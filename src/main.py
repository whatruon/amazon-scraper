"""Apify Actor entry point for the Amazon scraper.

Runs the sync scraping engine (Playwright + CloakBrowser) in a background
thread and streams results into the Apify dataset from the event loop.
Resume state is persisted to the key-value store so interrupted runs can
continue where they left off.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading

from apify import Actor, Event

from scraper.browser import BrowserSession
from scraper.orchestrator import ScrapeOrchestrator

from .actor_util import domain_for_urls, normalize_input, resolve_mode

log = logging.getLogger(__name__)

STATE_KEY = "STATE"
MAX_STATUS_INTERVAL = 5

_INPUT_REQUIRED_MSG = (
    "Actor input must provide either 'searchTerm' or 'productUrls' "
    "to scrape something"
)


def _require_input(input_data: dict) -> None:
    """Raise when the actor input has nothing to scrape."""
    if not input_data.get("searchTerm") and not input_data.get("productUrls"):
        raise ValueError(_INPUT_REQUIRED_MSG)


def _reraise(exc: BaseException) -> None:
    raise exc


async def main() -> None:
    await Actor.init()

    try:
        input_data = normalize_input(await Actor.get_input())
        mode = resolve_mode(input_data)
        log.info("Mode: %s", mode)

        _require_input(input_data)

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=input_data.get("proxy"),
        )
        proxy_url = None
        if proxy_configuration is not None:
            session_id = input_data.get("session") or None
            proxy_url = await proxy_configuration.new_url(session_id=session_id)
            if proxy_url:
                log.info("Using Apify proxy (session: %s)", session_id or "auto-rotated")
            else:
                log.warning("Apify proxy configuration produced no URL; scraping without proxy")

        urls: list[str] = []
        if mode == "urls":
            urls = list(input_data["productUrls"])
            detected = domain_for_urls(urls)
            if detected and input_data["domain"] == "amazon.com":
                input_data["domain"] = detected
                log.info("Detected domain from URL: %s", detected)

        resume = not input_data.get("freshRun", False)
        done: set[str] = set()
        if resume:
            state = await Actor.get_value(STATE_KEY) or {}
            done = set(state.get("processed", []))
            if done:
                log.info("Resuming: %d URL(s) already processed", len(done))

        # `stop` and `done` are shared between the event loop and the background
        # sync engine thread; `done` must only be touched under `done_lock`.
        stop = threading.Event()
        done_lock = threading.Lock()

        def _is_done(url: str | None) -> bool:
            with done_lock:
                return url in done

        def _mark_done(url: str) -> None:
            with done_lock:
                done.add(url)

        def _done_snapshot() -> list[str]:
            with done_lock:
                return sorted(done)

        async def _persist_handler() -> None:
            # PERSIST_STATE: save resume state only, keep scraping.
            await Actor.set_value(STATE_KEY, {"processed": _done_snapshot()})

        async def _stop_handler() -> None:
            # ABORTING / MIGRATING / EXIT: save state and stop the engine thread.
            await Actor.set_value(STATE_KEY, {"processed": _done_snapshot()})
            stop.set()

        Actor.on(Event.PERSIST_STATE, _persist_handler)
        Actor.on(Event.ABORTING, _stop_handler)
        Actor.on(Event.MIGRATING, _stop_handler)
        Actor.on(Event.EXIT, _stop_handler)

        session = BrowserSession(
            headless=True,
            proxy=proxy_url,
            domain=input_data["domain"],
        )
        orch = ScrapeOrchestrator(
            session=session,
            zip_code=input_data["zip"],
            max_results=input_data["maxResults"],
            max_pages=input_data["maxPages"],
            max_reviews=input_data["maxReviews"],
            retries=input_data["retries"],
            timeout=input_data["timeout"],
            wait=input_data["wait"],
            verbose=input_data["verbose"],
        )

        events: queue.Queue = queue.Queue()

        def sync_engine() -> None:
            session.start()
            try:
                if mode == "search":

                    def on_product(product) -> None:
                        if _is_done(product.url):
                            return
                        events.put(("product", product))

                    orch.scrape_search(
                        input_data["searchTerm"],
                        on_product=on_product,
                        should_stop=stop.is_set,
                    )
                else:
                    for url in urls:
                        if stop.is_set():
                            break
                        if _is_done(url):
                            continue
                        product = orch.scrape_product(url, should_stop=stop.is_set)
                        if product:
                            events.put(("product", product))
                events.put(("done", None))
            except Exception as exc:
                events.put(("error", exc))
            finally:
                session.stop()

        thread = threading.Thread(target=sync_engine, daemon=True, name="scraper-engine")
        thread.start()

        scraped = 0
        while True:
            kind, payload = await asyncio.to_thread(events.get)
            if kind == "product":
                await Actor.push_data(payload.to_dict())
                if payload.url:
                    _mark_done(payload.url)
                scraped += 1
                if scraped == 1 or scraped % MAX_STATUS_INTERVAL == 0:
                    await Actor.set_status_message(f"Scraped {scraped} products so far...")
            elif kind == "error":
                _reraise(payload)
            else:  # done
                break

        await Actor.set_status_message(f"Scraping finished: {scraped} product(s)")
        await Actor.exit(exit_code=0, status_message=f"Scraped {scraped} product(s)")

    except Exception as exc:
        log.exception("Actor failed")
        await Actor.fail(exit_code=1, exception=exc, status_message=str(exc))
