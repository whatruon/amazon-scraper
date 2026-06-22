from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page
from cloakbrowser import launch, launch_persistent_context

from .models import ScrapeError

log = logging.getLogger(__name__)


class BrowserSession:
    def __init__(
        self,
        headless: bool = True,
        humanize: bool = False,
        proxy: Optional[str] = None,
        geoip: bool = False,
        fingerprint: Optional[str] = None,
        user_agent: Optional[str] = None,
        persistent: Optional[str] = None,
        profile_dir: Path = Path("profiles"),
    ):
        self.headless = headless
        self.humanize = humanize
        self.proxy = proxy
        self.geoip = geoip
        self.fingerprint = fingerprint
        self.user_agent = user_agent
        self.persistent_name = persistent
        self.profile_dir = profile_dir

        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._owns_browser = False

    def start(self) -> None:
        kwargs = {
            "headless": self.headless,
            "humanize": self.humanize,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
            if self.geoip:
                kwargs["geoip"] = True
        if self.fingerprint:
            kwargs["args"] = [f"--fingerprint={self.fingerprint}"]

        if self.persistent_name:
            profile_path = self.profile_dir / self.persistent_name
            profile_path.mkdir(parents=True, exist_ok=True)
            self.context = launch_persistent_context(str(profile_path), **kwargs)
            self._owns_browser = False
        else:
            self.browser = launch(**kwargs)
            self.context = self.browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            self._owns_browser = True

    def stop(self) -> None:
        if self.context and not self.persistent_name:
            self.context.close()
        if self.browser and self._owns_browser:
            self.browser.close()

    def new_page(self) -> Page:
        return self.context.new_page()

    def set_zip_code(self, zip_code: str, verbose: bool = False) -> Page:
        page = self.new_page()
        try:
            page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)

            trigger = page.query_selector("#nav-global-location-popover-link")
            if trigger:
                trigger.click()
                page.wait_for_timeout(3000)
            else:
                if verbose:
                    log.info("Location popover not found on homepage")
                return page

            inputs = page.query_selector_all(
                "input.a-input-text, "
                "input[aria-label*='zip' i], "
                "input[aria-label*='code' i], "
                "input[name*='zip'], "
                ".a-popover-content input:not([type='hidden'])"
            )
            zip_input = None
            for inp in inputs:
                if inp.is_visible():
                    zip_input = inp
                    break

            if not zip_input:
                try:
                    zip_input = page.wait_for_selector(
                        "input:not([type='hidden']):not([type='submit']):not([type='button'])",
                        timeout=3000,
                    )
                except Exception:
                    pass

            if zip_input:
                try:
                    zip_input.evaluate("el => el.click()")
                except Exception:
                    zip_input.click()
                zip_input.fill("")
                zip_input.type(zip_code, delay=50)
                page.wait_for_timeout(1000)

                apply_btn = page.query_selector(
                    "button:has-text('Apply'), button:has-text('Done'), "
                    "input[type='submit']"
                )
                if apply_btn:
                    apply_btn.evaluate("el => el.click()")
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(3000)

                if verbose:
                    log.info("Zip code set to %s on amazon.com", zip_code)
            else:
                if verbose:
                    log.warning("No visible input found in location modal")

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

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
