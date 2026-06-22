from __future__ import annotations

import logging
import random
import time
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .models import ScrapeError

log = logging.getLogger(__name__)


class BrowserSession:
    """Connects to a remote CloakBrowser-manager profile over CDP.

    The manager profile owns its own fingerprint, proxy, and (US) location, so
    there are no local launch knobs here — just the CDP endpoint and auth.
    """

    def __init__(self, cdp_url: str, cdp_headers: Optional[dict] = None):
        self.cdp_url = cdp_url
        self.cdp_headers = cdp_headers or {}
        self._pw = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(
            self.cdp_url, headers=self.cdp_headers
        )
        self.context = (
            self.browser.contexts[0]
            if self.browser.contexts
            else self.browser.new_context()
        )

    def stop(self) -> None:
        # Leave the remote profile running; just drop our connection.
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def new_page(self) -> Page:
        return self.context.new_page()

    def set_zip_code(self, zip_code: str, verbose: bool = False) -> Page:
        # Drive Amazon's GLUX location widget by its stable element IDs. The old
        # fuzzy "first visible input + any submit" approach typed the zip but
        # never committed it, leaving the glow location on the IP's country
        # (e.g. Iraq) — which makes Amazon suppress the price block entirely.
        page = self.new_page()
        try:
            page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)

            trigger = page.query_selector("#nav-global-location-popover-link")
            if not trigger:
                if verbose:
                    log.info("Location popover not found on homepage")
                return page

            # The popover sometimes fails to open on first click; retry, and if a
            # non-US country is selected the US zip field only appears after switching.
            zip_input = None
            for attempt in range(3):
                trigger.evaluate("el => el.click()")
                for _ in range(8):
                    page.wait_for_timeout(1000)
                    zip_input = page.query_selector("#GLUXZipUpdateInput")
                    if zip_input:
                        break
                    country = page.query_selector("#GLUXCountryList")
                    if country:
                        country.select_option("US")
                if zip_input:
                    break
            if not zip_input:
                raise RuntimeError("GLUX zip input never appeared")

            zip_input.fill(zip_code)
            # JS-click: the GLUX apply/confirm controls fail Playwright's
            # actionability checks (wrapper spans, animated popover).
            apply = page.query_selector("#GLUXZipUpdate input[type='submit'], #GLUXZipUpdate-announce")
            if apply:
                apply.evaluate("el => el.click()")
            else:
                page.keyboard.press("Enter")
            page.wait_for_timeout(2500)

            # A "Done"/confirm step often follows; dismiss it to persist the cookie.
            confirm = page.query_selector(
                "button[name='glowDoneButton'], .a-popover-footer input[type='submit'], #GLUXConfirmClose"
            )
            if confirm:
                confirm.evaluate("el => el.click()")
            page.wait_for_timeout(2000)

            if verbose:
                loc = page.evaluate(
                    "() => { const e = document.getElementById('glow-ingress-line2'); return e ? e.innerText.trim() : '?'; }"
                )
                log.info("Zip set to %s; glow location now: %s", zip_code, loc)

        except Exception as e:
            if verbose:
                log.warning("Could not set zip code: %s", e)

        return page

    def navigate_with_retry(
        self,
        url: str,
        retries: int = 3,
        timeout: int = 30000,
        wait: int = 5000,
        verbose: bool = False,
    ) -> Page:
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            page = self.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(3000)

                capthca_btn = page.query_selector("button[alt='Continue shopping']")
                if capthca_btn:
                    if verbose:
                        log.info("CAPTCHA detected, clicking through...")
                    capthca_btn.click()
                    page.wait_for_timeout(5000)

                page.wait_for_timeout(wait)
                return page

            except Exception as e:
                last_exc = e
                page.close()
                if verbose:
                    log.warning("Attempt %d/%d failed: %s", attempt + 1, retries, e)
                if attempt < retries - 1:
                    delay = 2**attempt + random.uniform(0, 1)
                    time.sleep(delay)

        raise ScrapeError(url, str(last_exc), "navigation") from last_exc
