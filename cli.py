from __future__ import annotations

import argparse
import json
import logging
import re
import signal
import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from scraper import BrowserSession, HtmlCache, ScrapeError
from scraper.cache import atomic_write
from scraper.config import (
    AMAZON_TRACKING_PARAMS,
    CONFIG_KEYS,
    DEFAULT_CACHE_TTL,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MAX_REVIEWS,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_ZIP_CODE,
    load_config,
)
from scraper.masking import mask_proxy_credentials
from scraper.orchestrator import ScrapeOrchestrator

log = logging.getLogger("scraper")

_interrupted = False


def _handle_interrupt(signum: int, frame) -> None:
    """Set interrupt flag for graceful shutdown.  Call twice to force exit."""
    global _interrupted
    if _interrupted:
        sys.exit(1)
    _interrupted = True
    log.warning("Interrupt received — finishing current request, then saving partial results...")


def _get_amazon_domain(url: str) -> str:
    parsed = urlparse(url)
    # parsed.hostname strips the port and lowercases; fall back to netloc for
    # malformed URLs. If neither yields a host, the "amazon" check below
    # falls through to the default domain.
    host = (parsed.hostname or parsed.netloc).lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("smile."):
        host = host[6:]
    if "amazon" in host:
        return host
    return "amazon.com"


def _clean_amazon_url(url: str) -> str:
    """Remove tracking query params that can trigger CAPTCHA."""
    parsed = urlparse(url)
    if "amazon" not in parsed.netloc:
        return url
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if k not in AMAZON_TRACKING_PARAMS}
    clean = parsed._replace(query=urlencode(clean_qs, doseq=True)) if clean_qs else parsed._replace(query="")
    # Path-based refs (e.g. /dp/ASIN/ref=sr_1_1) are tracking too.
    path = re.sub(r"/ref=[^/]*/?$", "", clean.path)
    if path != clean.path:
        clean = clean._replace(path=path)
    return clean.geturl()


def main() -> None:
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)

    parser = argparse.ArgumentParser(
        description="Scrape Amazon product details via CloakBrowser"
    )
    parser.add_argument("--config", metavar="PATH", default="config.yaml",
                        help="YAML config file with default option values (default: config.yaml)")
    parser.add_argument(
        "url",
        help=(
            "Amazon product URL (e.g. https://www.amazon.com/dp/B09XS7JWHH) "
            "or search term (with -s/--search)"
        ),
    )
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--headed", action="store_true", help="Show browser UI")
    parser.add_argument("--proxy", help="Proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--geoip", action="store_true", help="Auto-detect timezone/locale from proxy IP")
    parser.add_argument("--fingerprint", help="Fixed fingerprint seed for consistent identity")
    parser.add_argument("--persistent", metavar="NAME", help="Use persistent profile (name for profile dir)")
    parser.add_argument("--user-agent", help="Custom user agent string")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help="Maximum attempts per product, including the first (default: %(default)s)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Navigation timeout in ms")
    parser.add_argument("--wait", type=int, default=0, help="Extra wait time after page load (ms)")
    parser.add_argument("--zip", default=DEFAULT_ZIP_CODE, help="Set delivery zip code (default: 90035)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-s", "--search", action="store_true", help="Treat URL as a search term instead of product URL")
    parser.add_argument(
        "-n", "--max-results", type=int, default=DEFAULT_MAX_RESULTS,
        help="Maximum number of search results to scrape (default: %(default)s)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=DEFAULT_MAX_PAGES,
        help="Maximum number of search result pages to walk (default: %(default)s)",
    )
    parser.add_argument(
        "--max-reviews", type=int, default=DEFAULT_MAX_REVIEWS,
        help="Maximum number of reviews to scrape per product; 0 disables (default: %(default)s)",
    )
    parser.add_argument("--cache", action="store_true", help="Enable HTML caching (reuse previously fetched pages)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable HTML caching even if enabled in config")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache/)")
    parser.add_argument("--cache-ttl", type=int, default=DEFAULT_CACHE_TTL, help="Cache TTL in seconds (default: 3600)")
    parser.add_argument(
        "--profile-dir", default="profiles",
        help="Directory for persistent profiles (default: profiles/)",
    )
    parser.add_argument("--domain", help="Amazon domain (e.g. amazon.co.uk). Overrides auto-detection from URL.")
    # Pre-parse so the config file itself can seed defaults for the rest.
    pre_args, _ = parser.parse_known_args()
    cfg = load_config(pre_args.config)
    if "headless" in cfg and "headed" not in cfg:
        # Config speaks in headless terms; the CLI flag is the inverse.
        cfg["headed"] = not bool(cfg.pop("headless"))
    if cfg:
        known = {k: v for k, v in cfg.items() if k in CONFIG_KEYS}
        if known:
            parser.set_defaults(**known)
    args = parser.parse_args()
    # Coerce numeric options (YAML may deliver them as strings) before use.
    try:
        for name in ("retries", "timeout", "wait", "max_results", "max_pages", "max_reviews", "cache_ttl"):
            if isinstance(getattr(args, name), str):
                setattr(args, name, int(getattr(args, name)))
    except ValueError:
        parser.error("config/CLI numeric option must be an integer")
    # Retries is the number of attempts; a value of 0 would skip scraping entirely.
    args.retries = max(1, args.retries)
    # YAML zip can come through as an int (unquoted 90035); zip_input.type() only accepts str.
    # A null zip in config must fall back to the default, not become the string "None".
    args.zip = str(args.zip) if args.zip is not None else DEFAULT_ZIP_CODE

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    domain = args.domain if args.domain else _get_amazon_domain(args.url)
    session = BrowserSession(
        headless=not args.headed,
        proxy=args.proxy,
        geoip=args.geoip,
        fingerprint=args.fingerprint,
        user_agent=args.user_agent,
        persistent=args.persistent,
        profile_dir=Path(args.profile_dir),
        domain=domain,
    )

    cache = HtmlCache(args.cache_dir, args.cache_ttl) if args.cache and not args.no_cache else None

    all_products: list = []
    product = None

    orch = ScrapeOrchestrator(
        session=session,
        cache=cache,
        zip_code=args.zip,
        max_results=args.max_results,
        max_pages=args.max_pages,
        max_reviews=args.max_reviews,
        retries=args.retries,
        timeout=args.timeout,
        wait=args.wait,
        verbose=args.verbose,
    )

    try:
        session.start()

        clean_url = _clean_amazon_url(args.url)
        if clean_url != args.url and args.verbose:
            log.info("Cleaned URL: %s", clean_url)

        if args.search:
            # Search mode: the orchestrator searches, then scrapes each result URL.
            all_products = orch.scrape_search(args.url, should_stop=lambda: _interrupted)

            output_data = [p.to_dict() for p in all_products]
            json_output = json.dumps(output_data, indent=2, ensure_ascii=False)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(out_path, json_output)
            else:
                print(json_output)  # noqa: T201  # CLI stdout output

        else:
            # Product mode (original behavior)
            product = orch.scrape_product(clean_url, should_stop=lambda: _interrupted)

            if product is None:
                # scrape_product returns None only when a graceful stop fired.
                log.warning("Scrape interrupted before completion")
                sys.exit(0)

            if args.verbose:
                log.info("URL: %s", args.url)
                log.info("Title: %s", product.title)
                log.info("Price: %s", product.price)
                log.info("Rating: %s", product.rating)
                log.info("Reviews: %s", product.review_count)
                log.info("ASIN: %s", product.asin)
                log.info("Availability: %s", product.availability)
                log.info("Images: %d", len(product.images))
                log.info("Bullet points: %d", len(product.bullets))

            output_dir = Path("output")
            output_dir.mkdir(parents=True, exist_ok=True)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                asin = "product"
                m = re.search(r"/dp/([A-Z0-9]{10})", args.url)
                if m:
                    asin = m.group(1)
                else:
                    m = re.search(r"/gp/product/([A-Z0-9]{10})", args.url)
                    if m:
                        asin = m.group(1)
                out_path = output_dir / f"{asin}.json"

            json_output = product.to_json()
            atomic_write(out_path, json_output)
            print(json_output)  # noqa: T201  # CLI stdout output

    except ScrapeError as e:
        # Only the masked message is logged; a traceback is not wanted here.
        log.error("%s", mask_proxy_credentials(str(e)))  # noqa: TRY400
        sys.exit(1)

    except Exception:
        # Mask proxy credentials before logging, since the traceback may
        # include them in the underlying exception message. The traceback is
        # formatted explicitly so credentials can be masked, hence log.error.
        log.error(  # noqa: TRY400
            "Unexpected error: %s", mask_proxy_credentials(traceback.format_exc())
        )
        sys.exit(1)

    finally:
        if _interrupted and (all_products or product):
            if not all_products:
                all_products = [product]
            partial = [p.to_dict() for p in all_products]
            partial_path = (
                Path(args.output).with_suffix(".partial.json")
                if args.output
                else Path("output") / "partial.json"
            )
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(partial_path, json.dumps(partial, indent=2, ensure_ascii=False))
            log.warning("Saved %d partial result(s) to %s", len(all_products), partial_path)
        session.stop()


if __name__ == "__main__":
    main()
