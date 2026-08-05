"""Tests for the orchestration layer."""  # noqa: INP001
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scraper.models import Product, SearchResult
from scraper.orchestrator import ScrapeOrchestrator


def _make_session():
    session = MagicMock()
    session.navigate_with_retry.return_value = MagicMock()
    return session


_PRODUCT_HTML = (
    "<html><body>"
    "<span id='productTitle'>P</span>"
    "<span id='priceblock_ourprice'>$29.99</span>"
    "</body></html>"
)


class TestScrapeOrchestrator:

    def test_run_search_scrapes_result_urls(self):
        """Search results (SearchResult objects) must be scraped by their .url."""
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        orch = ScrapeOrchestrator(session, verbose=False)
        result = SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1")

        orch._scrape_single_url(result.url)
        assert session.navigate_with_retry.call_args[0][0] == "https://www.amazon.com/dp/B0TESTABC1"

    def test_run_search_passes_urls_to_single_scraper(self, monkeypatch):
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        fake_results = [
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC2", asin="B0TESTABC2"),
        ]
        monkeypatch.setattr("scraper.orchestrator.search_amazon_func", lambda *a, **k: fake_results)

        orch = ScrapeOrchestrator(session, verbose=False)
        products = orch.scrape_search("test query")

        assert len(products) == 2
        assert all(isinstance(p, Product) for p in products)
        calls = [c.args[0] for c in session.navigate_with_retry.call_args_list]
        assert calls == [
            "https://www.amazon.com/dp/B0TESTABC1",
            "https://www.amazon.com/dp/B0TESTABC2",
        ]

    def test_search_forwards_max_pages_timeout_wait(self, monkeypatch):
        """Search must forward max_pages/timeout/wait to search_amazon."""
        captured = {}

        def _fake_search(*args, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr("scraper.orchestrator.search_amazon_func", _fake_search)
        session = _make_session()

        orch = ScrapeOrchestrator(
            session, max_pages=7, timeout=9000, wait=250, verbose=False,
        )
        orch.scrape_search("query")

        assert captured["max_pages"] == 7
        assert captured["timeout"] == 9000
        assert captured["wait"] == 250

    def test_page_closed_when_parsing_fails(self):
        """A page must be closed even when scraping raises mid-way.

        After all retries the last exception is re-raised (never swallowed), so
        callers like scrape_search can decide how to handle per-URL failures.
        """
        session = _make_session()
        page = MagicMock()
        page.content.side_effect = RuntimeError("boom")
        session.navigate_with_retry.return_value = page

        orch = ScrapeOrchestrator(session, retries=1, verbose=False)
        with pytest.raises(RuntimeError, match="boom"):
            orch._scrape_single_url("https://www.amazon.com/dp/B0TESTABC1")

        page.close.assert_called_once_with()

    def test_page_closed_on_success(self):
        """A page must be closed exactly once on the success path."""
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        orch = ScrapeOrchestrator(session, retries=1, verbose=False)
        product = orch._scrape_single_url("https://www.amazon.com/dp/B0TESTABC1")

        assert product is not None
        page.close.assert_called_once_with()

    def test_on_product_callback_receives_products(self, monkeypatch):
        """scrape_search must stream products through the on_product callback."""
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        fake_results = [
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC2", asin="B0TESTABC2"),
        ]
        monkeypatch.setattr("scraper.orchestrator.search_amazon_func", lambda *a, **k: fake_results)

        orch = ScrapeOrchestrator(session, retries=1, verbose=False)
        streamed = []
        orch.scrape_search("test query", on_product=streamed.append)

        assert [p.asin for p in streamed] == ["B0TESTABC1", "B0TESTABC2"]
        assert [p.url for p in streamed] == [
            "https://www.amazon.com/dp/B0TESTABC1",
            "https://www.amazon.com/dp/B0TESTABC2",
        ]

    def test_should_stop_halts_between_results(self, monkeypatch):
        """should_stop must break out of the search loop between results."""
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        fake_results = [
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC2", asin="B0TESTABC2"),
            SearchResult(url="https://www.amazon.com/dp/B0TESTABC3", asin="B0TESTABC3"),
        ]
        monkeypatch.setattr("scraper.orchestrator.search_amazon_func", lambda *a, **k: fake_results)

        stop_calls = {"count": 0}

        def should_stop():
            stop_calls["count"] += 1
            return stop_calls["count"] > 3

        orch = ScrapeOrchestrator(session, retries=1, verbose=False)
        products = orch.scrape_search("test query", should_stop=should_stop)

        assert len(products) == 1

    def test_product_url_stamped_on_product(self):
        """The scraped URL must be attached to the Product."""
        session = _make_session()
        page = MagicMock()
        page.content.return_value = _PRODUCT_HTML
        session.navigate_with_retry.return_value = page

        orch = ScrapeOrchestrator(session, retries=1, verbose=False)
        product = orch._scrape_single_url("https://www.amazon.com/dp/B0TESTABC1")

        assert product.url == "https://www.amazon.com/dp/B0TESTABC1"
