"""Tests for BrowserSession lifecycle and utility functions."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper.browser import BrowserSession, DOMAIN_LOCALE, VIEWPORTS, TIMEZONE_LOCALE


# ------------------------------------------------------------------
# Constructor
# ------------------------------------------------------------------

class TestConstructor:

    def test_defaults(self):
        session = BrowserSession()
        assert session.headless is True
        assert session.humanize is True
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

    def test_humanize_off(self):
        session = BrowserSession(humanize=False)
        assert session.humanize is False

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
def _scraper_mod():
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

    def test_clean_removes_tracking_params(self, _scraper_mod):
        url = "https://www.amazon.com/dp/B09XS7JWHH?tag=foobar&ref=sr_1_1&th=1"
        cleaned = _scraper_mod._clean_amazon_url(url)
        assert cleaned == "https://www.amazon.com/dp/B09XS7JWHH"

    def test_clean_preserves_no_tracking(self, _scraper_mod):
        url = "https://www.amazon.com/dp/B09XS7JWHH"
        assert _scraper_mod._clean_amazon_url(url) == url

    def test_clean_non_amazon_url(self, _scraper_mod):
        url = "https://example.com/page?foo=bar"
        assert _scraper_mod._clean_amazon_url(url) == url

    def test_get_domain(self, _scraper_mod):
        assert _scraper_mod._get_amazon_domain("https://www.amazon.com/dp/ASIN") == "amazon.com"
        assert _scraper_mod._get_amazon_domain("https://amazon.co.uk/dp/ASIN") == "amazon.co.uk"
        assert _scraper_mod._get_amazon_domain("https://example.com") == "amazon.com"
