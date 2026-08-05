from __future__ import annotations

import contextlib
import logging
import random
import re
import time
from pathlib import Path

from cloakbrowser import launch, launch_persistent_context
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .config import DOMAIN_LOCALE, TIMEZONE_LOCALE, VIEWPORTS
from .errors import BlockedError, CaptchaError, NavigationError, NavigationTimeout
from .masking import mask_proxy_credentials

log = logging.getLogger(__name__)


def _page_looks_like_captcha(page: Page) -> bool:
    """Best-effort detection of Amazon's CAPTCHA / robot-check page.

    Returns True when the page carries any of the well-known CAPTCHA
    indicators. Non-product pages without these indicators are not treated
    as CAPTCHAs.
    """
    if page.query_selector("#captcha-form"):
        return True
    if page.query_selector("input[name='captcha']"):
        return True
    try:
        title = page.title()
    except Exception:
        title = ""
    return bool(title) and re.search(r"robot check|captcha", title, re.IGNORECASE) is not None


class BrowserSession:
    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        geoip: bool = False,
        fingerprint: str | None = None,
        user_agent: str | None = None,
        persistent: str | None = None,
        profile_dir: Path = Path("profiles"),
        domain: str = "amazon.com",
    ):
        self.headless = headless
        self.proxy = proxy
        self.geoip = geoip
        self.fingerprint = fingerprint
        self.user_agent = user_agent
        self.persistent_name = persistent
        self.profile_dir = profile_dir
        self.domain = domain

        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self._owns_browser = False
        self._stopped = False

    def start(self) -> None:
        kwargs = {
            "headless": self.headless,
        }

        dl = DOMAIN_LOCALE.get(self.domain)
        if dl:
            kwargs["timezone"] = dl[0]
            kwargs["locale"] = dl[1]
        else:
            tz, locale = random.choice(TIMEZONE_LOCALE)  # noqa: S311
            kwargs["timezone"] = tz
            kwargs["locale"] = locale

        if self.proxy:
            kwargs["proxy"] = self.proxy
            if self.geoip:
                kwargs["geoip"] = True
        elif self.geoip:
            log.warning("--geoip requires --proxy; timezone/locale will not be geo-detected")
        if self.fingerprint:
            kwargs.setdefault("args", [])
            kwargs["args"].append(f"--fingerprint={self.fingerprint}")

        if self.persistent_name:
            name = self.persistent_name.replace("/", "_").replace("\\", "_").replace("..", "_")
            profile_path = self.profile_dir / name
            profile_path.mkdir(parents=True, exist_ok=True)
            kwargs["user_agent"] = self.user_agent
            kwargs["viewport"] = random.choice(VIEWPORTS)  # noqa: S311
            self.context = launch_persistent_context(str(profile_path), **kwargs)
            self._owns_browser = False
        else:
            self.browser = launch(**kwargs)
            self.context = self.browser.new_context(
                user_agent=self.user_agent,
                viewport=random.choice(VIEWPORTS),  # noqa: S311
            )
            self._owns_browser = True

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self.context:
            with contextlib.suppress(Exception):
                self.context.close()
        if self.browser:
            with contextlib.suppress(Exception):
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

        except Exception:
            # This is a best-effort function to set zip code; broader exception
            # handling is acceptable as certain page elements may be missing.
            if verbose:
                log.warning("Could not set zip code")

    def navigate_with_retry(
        self,
        url: str,
        retries: int = 2,
        timeout: int = 15000,
        wait: int = 0,
        verbose: bool = False,
    ) -> Page:
        last_exc: Exception | None = None
        captcha_seen = False
        for attempt in range(retries):
            page = None
            try:
                page = self.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                captcha_btn = page.query_selector("button[alt='Continue shopping']")
                if captcha_btn:
                    captcha_seen = True
                    log.warning("CAPTCHA detected on page")
                    if verbose:
                        log.info("CAPTCHA detected, clicking through...")
                    captcha_btn.click()
                    try:
                        page.wait_for_selector(
                            "#productTitle, #dp, #centerCol",
                            timeout=10000,
                        )
                    except Exception:
                        if verbose:
                            log.warning("CAPTCHA click did not resolve, re-navigating...")
                        # Reset page state instead of reusing the same (stale) instance
                        page.close()
                        page = self.new_page()
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                        try:
                            page.wait_for_selector(
                                "#productTitle, #dp, #centerCol",
                                timeout=10000,
                            )
                        except Exception as inner_e:
                            masked = mask_proxy_credentials(str(inner_e))
                            log.warning(
                                "CAPTCHA re-navigation did not resolve to product content: %s",
                                masked,
                            )
                            page.close()
                            raise CaptchaError(url, masked) from inner_e

                # Wait for core product content, not a flat timeout
                try:
                    page.wait_for_selector(
                        "#productTitle, #dp, #centerCol",
                        timeout=5000,
                    )
                except Exception:
                    # A CAPTCHA page must never be returned as a successful
                    # navigation; non-product pages without CAPTCHA indicators
                    # are still allowed through.
                    if _page_looks_like_captcha(page):
                        captcha_seen = True
                        reason = "CAPTCHA page served in place of product content"
                        page.close()
                        raise CaptchaError(url, reason) from None

            except CaptchaError:
                if page:
                    page.close()
                raise
            except Exception as e:
                last_exc = e
                if page:
                    page.close()
                if verbose:
                    log.warning(
                        "Attempt %d/%d failed: %s",
                        attempt + 1,
                        retries,
                        mask_proxy_credentials(str(e)),
                    )
                if attempt < retries - 1:
                    delay = 2**attempt + random.uniform(0, 1)  # noqa: S311
                    time.sleep(delay)
            else:
                if wait:
                    page.wait_for_timeout(wait)

                return page

        # Centralized error masking and classification
        error_msg = mask_proxy_credentials(str(last_exc))
        if isinstance(last_exc, PlaywrightTimeoutError):
            raise NavigationTimeout(url, error_msg) from last_exc
        if captcha_seen:
            raise CaptchaError(url, error_msg) from last_exc
        if last_exc and re.search(
            r"\b(?:503|509|403)\b|blocked|rate\s*limit|robot|bot\s*check",
            error_msg,
            re.IGNORECASE,
        ):
            raise BlockedError(url, error_msg) from last_exc
        raise NavigationError(url, error_msg) from last_exc
