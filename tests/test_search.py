"""Tests for search_amazon orchestration with mocked browser session."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scraper.search import search_amazon
from scraper.models import SearchResult


@pytest.fixture
def mock_page():
    """Create a mock Playwright Page with sensible defaults."""
    page = MagicMock()
    page.content.return_value = "<html><body>no results</body></html>"
    page.query_selector.return_value = None
    return page


@pytest.fixture
def mock_session(mock_page):
    """Create a mock BrowserSession that returns *mock_page* from new_page()."""
    session = MagicMock()
    session.new_page.return_value = mock_page
    session.domain = "www.amazon.com"
    return session


# ------------------------------------------------------------------
# Basic search scenarios
# ------------------------------------------------------------------

class TestSearch:

    def test_search_returns_results(self, mock_session, mock_page):
        """Verify search_amazon returns SearchResult objects when parse_search_results finds some."""
        search_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>Product 1</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST2"><span>Product 2</span></a></h2>
            </div>
        </body></html>
        """
        mock_page.content.return_value = search_html

        results = search_amazon(mock_session, "test query", max_results=5, verbose=False)

        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        assert "https://www.amazon.com/dp/B0TEST1" in [r.url for r in results]
        assert "https://www.amazon.com/dp/B0TEST2" in [r.url for r in results]

    def test_search_empty_results(self, mock_session, mock_page):
        """Verify search_amazon returns empty list when no results found."""
        mock_page.content.return_value = "<html><body>no results here</body></html>"

        results = search_amazon(mock_session, "nothing", max_results=5, verbose=False)

        assert results == []

    def test_search_no_duplicate_urls(self, mock_session, mock_page):
        """Verify duplicate URLs are not returned."""
        search_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>Product 1</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>Product 1 again</span></a></h2>
            </div>
        </body></html>
        """
        mock_page.content.return_value = search_html

        results = search_amazon(mock_session, "dupes", max_results=5, verbose=False)

        assert len(results) == 1
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_respects_max_results(self, mock_session, mock_page):
        """Verify max_results limits the returned URLs."""
        search_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>Product 1</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST2"><span>Product 2</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST3"><span>Product 3</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST4"><span>Product 4</span></a></h2>
            </div>
        </body></html>
        """
        mock_page.content.return_value = search_html

        urls = search_amazon(mock_session, "limit test", max_results=2, verbose=False)

        assert len(urls) == 2

    def test_search_uses_correct_url(self, mock_session, mock_page):
        """Verify the constructed search URL contains the query."""
        mock_page.content.return_value = "<html><body>no results</body></html>"

        search_amazon(mock_session, "wireless headphones", max_results=5, verbose=False)

        call_url = mock_page.goto.call_args[0][0]
        assert "k=wireless+headphones" in call_url
        assert "amazon.com/s?" in call_url

    def test_search_pagination(self, mock_session, mock_page):
        """Verify multiple pages are fetched when results exceed one page."""
        page1_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>P1</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST2"><span>P2</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST3"><span>P3</span></a></h2>
            </div>
        </body></html>
        """
        page2_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST4"><span>P4</span></a></h2>
            </div>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST5"><span>P5</span></a></h2>
            </div>
        </body></html>
        """
        mock_page.content.side_effect = [page1_html, page2_html]

        urls = search_amazon(mock_session, "pagination", max_results=5, verbose=False)

        assert len(urls) == 5
        assert mock_page.goto.call_count == 2


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

class TestSearchErrors:

    def test_navigation_failure_returns_empty(self, mock_session):
        """Verify search returns empty list when goto raises."""
        mock_page = mock_session.new_page.return_value
        mock_page.goto.side_effect = Exception("Navigation failed")

        urls = search_amazon(mock_session, "fail", max_results=5, verbose=False)

        assert urls == []

    def test_captcha_detected(self, mock_session, mock_page):
        """Verify CAPTCHA detection doesn't crash the search."""
        # Only return captcha_btn for the first page's CAPTCHA check.
        # Subsequent pages (same mock) get None so only one click fires.
        captcha_btn = MagicMock()
        mock_page.query_selector.side_effect = [captcha_btn] + [None] * 20

        search_html = """
        <html><body>
            <div data-component-type="s-search-result">
                <h2><a class="a-link-normal s-no-outline" href="/dp/B0TEST1"><span>Product</span></a></h2>
            </div>
        </body></html>
        """
        mock_page.content.return_value = search_html

        urls = search_amazon(mock_session, "captcha test", max_results=5, verbose=False)

        captcha_btn.click.assert_called_once()
        assert len(urls) == 1

    def test_page_content_returns_no_results_stops(self, mock_session, mock_page):
        """Verify search stops paginating when a page returns no results."""
        mock_page.content.return_value = "<html><body>no results</body></html>"

        urls = search_amazon(mock_session, "retry", max_results=5, verbose=False)

        assert urls == []
        # Only one page should be fetched before breaking
        assert mock_page.goto.call_count == 1


# ------------------------------------------------------------------
# Session new_page lifecycle
# ------------------------------------------------------------------

class TestSessionLifecycle:

    def test_new_page_called_for_each_page(self, mock_session, mock_page):
        """Verify new_page is called for each search results page."""
        mock_page.content.return_value = "<html><body>no results</body></html>"

        search_amazon(mock_session, "lifecycle", max_results=5, verbose=False)

        assert mock_session.new_page.call_count >= 1

    def test_page_closed_after_each_page(self, mock_session, mock_page):
        """Verify each page is closed after processing."""
        mock_page.content.return_value = "<html><body>no results</body></html>"

        search_amazon(mock_session, "cleanup", max_results=5, verbose=False)

        assert mock_page.close.called

    def test_session_start_not_called_by_search(self, mock_session, mock_page):
        """search_amazon does not call session.start() (caller's responsibility)."""
        mock_page.content.return_value = "<html><body>no results</body></html>"

        search_amazon(mock_session, "nostart", max_results=5, verbose=False)

        mock_session.start.assert_not_called()
