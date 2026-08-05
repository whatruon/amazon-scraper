"""Tests for BrowserSession lifecycle and utility functions."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scraper.browser import DOMAIN_LOCALE, TIMEZONE_LOCALE, VIEWPORTS, BrowserSession
from scraper.errors import BlockedError, CaptchaError, NavigationError, NavigationTimeout

# ------------------------------------------------------------------
# Constructor
# ------------------------------------------------------------------

class TestConstructor:

    def test_defaults(self):
        session = BrowserSession()
        assert session.headless is True
        assert session.proxy is None
        assert session.geoip is False
        assert session.fingerprint is None
        assert session.user_agent is None
        assert session.persistent_name is None
        assert session.profile_dir == Path("profiles")
        assert session.domain == "amazon.com"
        assert session.browser is None
        assert session.context is None
        assert session._owns_browser is False
        assert session._stopped is False

    def test_headless_off(self):
        session = BrowserSession(headless=False)
        assert session.headless is False

    def test_proxy(self):
        session = BrowserSession(proxy="http://user:pass@host:8080")
        assert session.proxy == "http://user:pass@host:8080"

    def test_geoip(self):
        session = BrowserSession(geoip=True)
        assert session.geoip is True

    def test_fingerprint(self):
        session = BrowserSession(fingerprint="abc123")
        assert session.fingerprint == "abc123"

    def test_user_agent(self):
        session = BrowserSession(user_agent="Mozilla/5.0 Custom")
        assert session.user_agent == "Mozilla/5.0 Custom"

    def test_persistent(self):
        session = BrowserSession(persistent="test-profile")
        assert session.persistent_name == "test-profile"

    def test_custom_profile_dir(self, tmp_path: Path):
        session = BrowserSession(profile_dir=tmp_path / "myprofiles")
        assert session.profile_dir == tmp_path / "myprofiles"

    def test_custom_domain(self):
        session = BrowserSession(domain="amazon.co.uk")
        assert session.domain == "amazon.co.uk"

    def test_geoip_without_proxy_warns(self, monkeypatch, caplog):
        """--geoip without --proxy must warn that it is a no-op."""
        fake_browser = MagicMock()
        fake_browser.new_context.return_value = MagicMock()
        monkeypatch.setattr("scraper.browser.launch", lambda **kwargs: fake_browser)

        session = BrowserSession(geoip=True)
        with caplog.at_level(logging.WARNING, logger="scraper.browser"):
            session.start()

        assert "geoip" in caplog.text.lower()
        assert "proxy" in caplog.text.lower()


# ------------------------------------------------------------------
# navigate_with_retry — error classification
# ------------------------------------------------------------------

class TestNavigateWithRetryErrors:

    def _session_with_page(self, page) -> BrowserSession:
        session = BrowserSession()
        context = MagicMock()
        context.new_page.return_value = page
        session.context = context
        return session

    def test_timeout_raises_navigation_timeout(self):
        page = MagicMock()
        page.goto.side_effect = PlaywrightTimeoutError("timeout exceeded")
        session = self._session_with_page(page)

        with pytest.raises(NavigationTimeout):
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

    def test_blocked_raises_blocked_error(self):
        page = MagicMock()
        page.goto.side_effect = Exception("net::ERR_ABORTED 503 Service Unavailable")
        session = self._session_with_page(page)

        with pytest.raises(BlockedError):
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

    def test_captcha_unresolved_raises_captcha_error(self):
        page1 = MagicMock()
        page2 = MagicMock()
        # page1: CAPTCHA button present; click resolves to nothing.
        page1.query_selector.return_value = MagicMock()
        page1.wait_for_selector.side_effect = PlaywrightTimeoutError("still captcha")
        # page2: re-navigation also fails.
        page2.goto.side_effect = Exception("navigation failed")

        session = BrowserSession()
        context = MagicMock()
        context.new_page.side_effect = [page1, page2]
        session.context = context

        with pytest.raises(CaptchaError):
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

    def test_generic_error_raises_navigation_error(self):
        page = MagicMock()
        page.goto.side_effect = RuntimeError("boom")
        session = self._session_with_page(page)

        with pytest.raises(NavigationError):
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

    def test_captcha_renavigation_failure_raises_captcha_error(self):
        """A CAPTCHA page must not be returned when the re-navigation also fails."""
        page1 = MagicMock()
        page2 = MagicMock()
        # page1: CAPTCHA button present; the click-through never resolves.
        page1.query_selector.return_value = MagicMock()
        page1.wait_for_selector.side_effect = PlaywrightTimeoutError("still captcha")
        # page2: re-navigation loads but product content never appears.
        page2.wait_for_selector.side_effect = PlaywrightTimeoutError("still captcha")

        session = BrowserSession()
        context = MagicMock()
        context.new_page.side_effect = [page1, page2]
        session.context = context

        with pytest.raises(CaptchaError) as exc_info:
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

        # The CaptchaError must be chained from the inner re-navigation failure.
        assert isinstance(exc_info.value.__cause__, PlaywrightTimeoutError)

    def test_captcha_page_detected_in_final_wait_raises(self):
        """A CAPTCHA page without the Continue-shopping button is not returned."""
        page = MagicMock()
        # No Continue-shopping button, but the page carries a captcha form.
        page.query_selector.side_effect = [None, MagicMock(), None]
        page.wait_for_selector.side_effect = PlaywrightTimeoutError("no product content")
        session = self._session_with_page(page)

        with pytest.raises(CaptchaError):
            session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)

    def test_non_captcha_page_without_product_selector_still_returns(self):
        """A non-product, non-CAPTCHA page is still returned as-is."""
        page = MagicMock()
        page.query_selector.return_value = None
        page.wait_for_selector.side_effect = PlaywrightTimeoutError("no product content")
        page.title.return_value = "Electronics Deals"
        session = self._session_with_page(page)

        result = session.navigate_with_retry("https://www.amazon.com/dp/ASIN1", retries=1)
        assert result is page


# ------------------------------------------------------------------
# stop() — idempotence and safety without start()
# ------------------------------------------------------------------

class TestStop:

    def test_stop_without_start(self):
        """Calling stop() without start() should be a no-op."""
        session = BrowserSession()
        session.stop()  # should not raise

    def test_stop_is_idempotent(self):
        """Calling stop() multiple times should not raise."""
        session = BrowserSession()
        session.stop()
        session.stop()  # should not raise

    def test_stop_sets_flag(self):
        session = BrowserSession()
        assert session._stopped is False
        session.stop()
        assert session._stopped is True

    def test_stop_closes_context(self):
        session = BrowserSession()
        session.context = MagicMock()
        session.stop()
        session.context.close.assert_called_once()

    def test_stop_closes_browser(self):
        session = BrowserSession()
        session.browser = MagicMock()
        session.stop()
        session.browser.close.assert_called_once()

    def test_stop_closes_both(self):
        session = BrowserSession()
        session.context = MagicMock()
        session.browser = MagicMock()
        session.stop()
        session.context.close.assert_called_once()
        session.browser.close.assert_called_once()

    def test_stop_idempotent_context_closed_once(self):
        """When called twice, the context should be closed only once."""
        session = BrowserSession()
        session.context = MagicMock()
        session.stop()
        session.stop()
        session.context.close.assert_called_once()


# ------------------------------------------------------------------
# Domain / locale constants
# ------------------------------------------------------------------

class TestDomainLocale:

    def test_all_amazon_domains_have_entries(self):
        known = {
            "amazon.ae", "amazon.co.uk", "amazon.de", "amazon.fr",
            "amazon.it", "amazon.es", "amazon.ca", "amazon.co.jp",
            "amazon.in", "amazon.com.au", "amazon.com.br", "amazon.com.mx",
            "amazon.nl", "amazon.se", "amazon.pl", "amazon.sg",
            "amazon.eg", "amazon.sa", "amazon.tr",
        }
        assert set(DOMAIN_LOCALE.keys()) == known

    def test_each_domain_has_tz_and_locale(self):
        for domain, (tz, locale) in DOMAIN_LOCALE.items():
            assert isinstance(domain, str), f"{domain} should be str"
            assert isinstance(tz, str), f"{domain} tz should be str"
            assert isinstance(locale, str), f"{domain} locale should be str"
            assert tz, f"{domain} tz is empty"
            assert locale, f"{domain} locale is empty"

    def test_all_timezones_are_valid_iana(self):
        """Basic sanity — each timezone should contain a '/'.
        A real IANA check requires pytz; this catches obvious typos."""
        import zoneinfo
        for domain, (tz, _) in DOMAIN_LOCALE.items():
            try:
                zoneinfo.ZoneInfo(tz)
            except (TypeError, zoneinfo.ZoneInfoNotFoundError):
                pytest.fail(f"{domain}: invalid timezone {tz!r}")


class TestViewports:

    def test_all_viewports_have_width_and_height(self):
        for vp in VIEWPORTS:
            assert "width" in vp
            assert "height" in vp
            assert isinstance(vp["width"], int)
            assert isinstance(vp["height"], int)
            assert vp["width"] > 0
            assert vp["height"] > 0

    def test_viewports_are_distinct(self):
        tuples = [(vp["width"], vp["height"]) for vp in VIEWPORTS]
        assert len(tuples) == len(set(tuples))


class TestTimezoneLocale:

    def test_each_entry_is_pair_of_strings(self):
        for item in TIMEZONE_LOCALE:
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], str)
            assert "/" in item[0]  # IANA timezone

    def test_timezones_are_valid_iana(self):
        import zoneinfo
        for tz, _ in TIMEZONE_LOCALE:
            try:
                zoneinfo.ZoneInfo(tz)
            except (TypeError, zoneinfo.ZoneInfoNotFoundError):
                pytest.fail(f"invalid timezone {tz!r}")


# ------------------------------------------------------------------
# URL cleaning (re-imported from scraper.py to avoid naming conflict)
# ------------------------------------------------------------------

@pytest.fixture(scope="session")
def scraper_mod():
    """Load cli.py (the CLI entry point) via an alias so 'scraper'
    still resolves to the 'scraper/' package for internal imports."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scraper_cli",
        "cli.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestUrlCleaning:

    def test_clean_removes_tracking_params(self, scraper_mod):
        url = "https://www.amazon.com/dp/B09XS7JWHH?tag=foobar&ref=sr_1_1&th=1"
        cleaned = scraper_mod._clean_amazon_url(url)
        assert cleaned == "https://www.amazon.com/dp/B09XS7JWHH"

    def test_clean_preserves_no_tracking(self, scraper_mod):
        url = "https://www.amazon.com/dp/B09XS7JWHH"
        assert scraper_mod._clean_amazon_url(url) == url

    def test_clean_removes_path_ref(self, scraper_mod):
        url = "https://www.amazon.com/dp/B09XS7JWHH/ref=sr_1_1?tag=foo&th=1"
        cleaned = scraper_mod._clean_amazon_url(url)
        assert cleaned == "https://www.amazon.com/dp/B09XS7JWHH"

    def test_clean_non_amazon_url(self, scraper_mod):
        url = "https://example.com/page?foo=bar"
        assert scraper_mod._clean_amazon_url(url) == url

    def test_clean_preserves_port(self, scraper_mod):
        """A port must survive URL cleaning while tracking params are dropped."""
        url = "https://www.amazon.com:8443/dp/B09XS7JWHH?tag=foo&th=1"
        cleaned = scraper_mod._clean_amazon_url(url)
        assert cleaned == "https://www.amazon.com:8443/dp/B09XS7JWHH"

    def test_get_domain(self, scraper_mod):
        assert scraper_mod._get_amazon_domain("https://www.amazon.com/dp/ASIN") == "amazon.com"
        assert scraper_mod._get_amazon_domain("https://amazon.co.uk/dp/ASIN") == "amazon.co.uk"
        assert scraper_mod._get_amazon_domain("https://example.com") == "amazon.com"


# ------------------------------------------------------------------
# set_zip_code
# ------------------------------------------------------------------

class TestSetZipCode:

    def test_skips_non_amazon_domain(self):
        """set_zip_code must be a no-op for non-amazon.com domains."""
        session = BrowserSession(domain="amazon.co.uk")
        page = MagicMock()
        session.set_zip_code(page, zip_code="12345")
        page.query_selector.assert_not_called()

    def test_returns_when_zip_already_set(self):
        """A delivery line that already shows a zip code short-circuits."""
        session = BrowserSession(domain="amazon.com")
        page = MagicMock()
        line2 = MagicMock()
        line2.inner_text.return_value = "Deliver to 90035"
        page.query_selector.return_value = line2
        session.set_zip_code(page, zip_code="90035")
        # Only the glow-ingress check ran; no modal was opened.
        page.query_selector.assert_called_once_with("#glow-ingress-line2")

    def test_full_flow_enters_and_applies_zip(self):
        """Happy path: open the modal, type the zip, apply, and confirm."""
        session = BrowserSession(domain="amazon.com")
        page = MagicMock()
        trigger = MagicMock()
        zip_input = MagicMock()
        apply_btn = MagicMock()
        done_btn = MagicMock()
        page.query_selector.side_effect = [
            None,        # #glow-ingress-line2 (no zip set yet)
            None,        # .glow-toaster (no toaster)
            None,        # #GLUXZipUpdateInput (modal not open yet)
            trigger,     # #nav-global-location-popover-link
            zip_input,   # #GLUXZipUpdateInput (modal now open)
            apply_btn,   # #GLUXZipUpdate input[type='submit']
            None,        # #GLUXZipError (no error)
            done_btn,    # button[name='glowDoneButton']
        ]
        session.set_zip_code(page, zip_code="10001")

        trigger.click.assert_called_once()
        zip_input.type.assert_called_once_with("10001", delay=50)
        apply_btn.click.assert_called_once()
        done_btn.click.assert_called_once()

    def test_validation_error_escapes_cleanly(self):
        """A rejected zip shows the error, presses Escape, and returns."""
        session = BrowserSession(domain="amazon.com")
        page = MagicMock()
        error_el = MagicMock()
        error_el.is_visible.return_value = True
        page.query_selector.side_effect = [
            None,        # #glow-ingress-line2
            None,        # .glow-toaster
            None,        # #GLUXZipUpdateInput (modal not open)
            MagicMock(),  # #nav-global-location-popover-link
            MagicMock(),  # #GLUXZipUpdateInput (modal now open)
            None,        # #GLUXZipUpdate input[type='submit'] (missing)
            None,        # #GLUXZipUpdate (missing -> keyboard Enter)
            error_el,    # #GLUXZipError (visible -> Escape)
        ]
        session.set_zip_code(page, zip_code="00000")
        page.keyboard.press.assert_called_with("Escape")
