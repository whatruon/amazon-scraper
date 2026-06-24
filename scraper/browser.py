from __future__ import annotations

import logging
import random
import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page
from cloakbrowser import launch, launch_persistent_context

from .models import ScrapeError

log = logging.getLogger(__name__)


VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
]

TIMEZONE_LOCALE = [
    ("America/New_York", "en-US"),
    ("America/Chicago", "en-US"),
    ("America/Denver", "en-US"),
    ("America/Los_Angeles", "en-US"),
]

DOMAIN_LOCALE: dict[str, tuple[str, str]] = {
    "amazon.ae": ("Asia/Dubai", "en-US"),
    "amazon.co.uk": ("Europe/London", "en-US"),
    "amazon.de": ("Europe/Berlin", "en-US"),
    "amazon.fr": ("Europe/Paris", "en-US"),
    "amazon.it": ("Europe/Rome", "en-US"),
    "amazon.es": ("Europe/Madrid", "en-US"),
    "amazon.ca": ("America/Toronto", "en-US"),
    "amazon.co.jp": ("Asia/Tokyo", "en-US"),
    "amazon.in": ("Asia/Kolkata", "en-US"),
    "amazon.com.au": ("Australia/Sydney", "en-US"),
    "amazon.com.br": ("America/Sao_Paulo", "en-US"),
    "amazon.com.mx": ("America/Mexico_City", "en-US"),
    "amazon.nl": ("Europe/Amsterdam", "en-US"),
    "amazon.se": ("Europe/Stockholm", "en-US"),
    "amazon.pl": ("Europe/Warsaw", "en-US"),
    "amazon.sg": ("Asia/Singapore", "en-US"),
    "amazon.eg": ("Africa/Cairo", "en-US"),
    "amazon.sa": ("Asia/Riyadh", "en-US"),
    "amazon.tr": ("Europe/Istanbul", "en-US"),
}


class BrowserSession:
    def __init__(
        self,
        headless: bool = True,
        humanize: bool = True,
        proxy: Optional[str] = None,
        geoip: bool = False,
        fingerprint: Optional[str] = None,
        user_agent: Optional[str] = None,
        persistent: Optional[str] = None,
        profile_dir: Path = Path("profiles"),
        domain: str = "amazon.com",
    ):
        self.headless = headless
        self.humanize = humanize
        self.proxy = proxy
        self.geoip = geoip
        self.fingerprint = fingerprint
        self.user_agent = user_agent
        self.persistent_name = persistent
        self.profile_dir = profile_dir
        self.domain = domain

        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._owns_browser = False

    def start(self) -> None:
        kwargs = {
            "headless": self.headless,
            "humanize": self.humanize,
        }
        if self.humanize:
            kwargs["human_preset"] = "careful"
            kwargs["human_config"] = {
                "typing_delay": 200,
                "typing_delay_spread": 100,
                "mouse_steps_divisor": 4,
                "mouse_max_steps": 120,
                "mouse_wobble_max": 3.0,
                "mouse_overshoot_chance": 0.2,
                "idle_between_actions": True,
                "idle_between_duration": (1.0, 2.5),
            }

        dl = DOMAIN_LOCALE.get(self.domain)
        if dl:
            kwargs["timezone"] = dl[0]
            kwargs["locale"] = dl[1]
        else:
            tz, locale = random.choice(TIMEZONE_LOCALE)
            kwargs["timezone"] = tz
            kwargs["locale"] = locale

        if self.proxy:
            kwargs["proxy"] = self.proxy
            if self.geoip:
                kwargs["geoip"] = True
        if self.fingerprint:
            kwargs.setdefault("args", [])
            kwargs["args"].append(f"--fingerprint={self.fingerprint}")

        if self.persistent_name:
            profile_path = self.profile_dir / self.persistent_name
            profile_path.mkdir(parents=True, exist_ok=True)
            self.context = launch_persistent_context(str(profile_path), **kwargs)
            self._owns_browser = False
        else:
            self.browser = launch(**kwargs)
            self.context = self.browser.new_context(
                user_agent=self.user_agent,
                viewport=random.choice(VIEWPORTS),
            )
            self._owns_browser = True

    def stop(self) -> None:
        if self.context:
            self.context.close()
        if self.browser and self._owns_browser:
            self.browser.close()

    def new_page(self) -> Page:
        return self.context.new_page()

    def set_zip_code(self, page: Page, zip_code: str = "90035", verbose: bool = False) -> None:
        if self.domain != "amazon.com":
            if verbose:
                log.info("Skipping zip code for domain: %s", self.domain)
            return
        try:
            line2 = page.query_selector("#glow-ingress-line2")
            if line2:
                text = line2.inner_text()
                if re.search(r"\b\d{5}\b", text):
                    if verbose:
                        log.info("Zip code already set: %s", text.strip())
                    return

            toaster = page.query_selector(".glow-toaster")
            if toaster and toaster.is_visible():
                sub = toaster.query_selector(".glow-toaster-button-submit")
                if sub:
                    sub.click()
                    page.wait_for_selector("#GLUXZipUpdateInput", timeout=5000)
                else:
                    d = toaster.query_selector(".glow-toaster-button-dismiss")
                    if d:
                        d.click()
                        page.wait_for_selector(".glow-toaster", state="hidden", timeout=5000)

            if not page.query_selector("#GLUXZipUpdateInput"):
                trigger = page.query_selector("#nav-global-location-popover-link")
                if not trigger:
                    if verbose:
                        log.warning("Location popover trigger not found")
                    return
                trigger.click()
                try:
                    page.wait_for_selector("#GLUXZipUpdateInput", timeout=5000)
                except Exception:
                    if verbose:
                        log.warning("Zip input modal did not appear")
                    return

            zip_input = page.query_selector("#GLUXZipUpdateInput")
            if not zip_input:
                if verbose:
                    log.warning("Zip input not found in modal")
                return

            zip_input.click()
            zip_input.fill("")
            zip_input.type(zip_code, delay=50)
            page.wait_for_selector("#GLUXZipUpdateInput", state="attached")

            apply_btn = page.query_selector("#GLUXZipUpdate input[type='submit']")
            if not apply_btn:
                apply_btn = page.query_selector("#GLUXZipUpdate")
            if apply_btn:
                apply_btn.click()
            else:
                page.keyboard.press("Enter")

            page.wait_for_selector("#GLUXZipUpdate", state="detached", timeout=10000)

            error_el = page.query_selector("#GLUXZipError:not(.GLUX_Hidden)")
            if error_el and error_el.is_visible():
                if verbose:
                    log.warning("Zip code validation error")
                page.keyboard.press("Escape")
                return

            page.wait_for_selector(".a-popover-inner, #GLUXZipUpdate", state="detached", timeout=5000)

            done_btn = page.query_selector("button[name='glowDoneButton']")
            if done_btn:
                done_btn.click()
            else:
                close_btns = page.query_selector_all(".a-popover-footer button")
                if close_btns:
                    close_btns[-1].click()
                else:
                    page.keyboard.press("Escape")

            page.wait_for_selector(".a-popover, #GLUXZipUpdateInput", state="hidden", timeout=5000)

            if verbose:
                log.info("Zip code set to %s", zip_code)

        except Exception as e:
            if verbose:
                log.warning("Could not set zip code: %s", e)

    def navigate_with_retry(
        self,
        url: str,
        retries: int = 2,
        timeout: int = 15000,
        wait: int = 0,
        verbose: bool = False,
    ) -> Page:
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            page = self.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                capthca_btn = page.query_selector("button[alt='Continue shopping']")
                if capthca_btn:
                    log.warning("CAPTCHA detected on page")
                    if verbose:
                        log.info("CAPTCHA detected, clicking through...")
                    capthca_btn.click()
                    try:
                        page.wait_for_selector(
                            "#productTitle, #dp, #centerCol",
                            timeout=10000,
                        )
                    except Exception:
                        pass
                    return page

                # Wait for core product content, not a flat timeout
                try:
                    page.wait_for_selector(
                        "#productTitle, #dp, #centerCol",
                        timeout=5000,
                    )
                except Exception:
                    pass

                if wait:
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
