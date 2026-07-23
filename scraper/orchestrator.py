from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Page

from .browser import BrowserSession
from .config import DEFAULT_MAX_PAGES, DEFAULT_MAX_RESULTS
from .errors import ParseError
from .models import Product
from .parser import enrich_from_browser, extract_price, parse_search_results, parse_search_card
from .search import search_amazon as search_amazon_func
from .seller import scrape_seller_info

log = logging.getLogger(__name__)


class ScrapeOrchestrator:
    """Orchestration layer for scraping products from Amazon.

    Consolidates the business logic from cli.py into a reusable class that can be
    used both from the CLI and potentially from other entry points.
    """

    def __init__(
        self,
        session: BrowserSession,
        cache=None,
        zip_code: str = "90035",
        max_results: int = DEFAULT_MAX_RESULTS,
        max_pages: int = DEFAULT_MAX_PAGES,
        verbose: bool = False,
    ) -> None:
        self.session = session
        self.cache = cache
        self.zip_code = zip_code
        self.max_results = max_results
        self.max_pages = max_pages
        self.verbose = verbose

    def _get_amazon_domain(self, url: str) -> str:
        # Reuse the domain extraction utility from cli.py
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if "amazon" in host:
            return host
        return "amazon.com"

    def _run_search(self, query: str) -> list[Product]:
        """Get product results for a search query.

        This method handles the business logic for searching Amazon and converting
        search results into Product objects.
        """
        # Use search_amazon to get URLs from search results
        urls = search_amazon_func(
            self.session,
            query,
            max_results=self.max_results,
            verbose=self.verbose,
        )

        # Convert URLs to Product objects by scraping each one
        products: list[Product] = []

        for url in urls:
            try:
                # Try to use cached HTML first if available
                if self.cache:
                    cached_html = self.cache.get(url)
                    if cached_html is not None:
                        product = self._parse_product_from_html(cached_html, url)
                        if self.verbose:
                            log.info("Using cached HTML for search result %s", url)
                        if product:
                            products.append(product)
                        continue

                # If not cached, scrape the URL
                page = self.session.navigate_with_retry(url)
                self.session.set_zip_code(page, zip_code=self.zip_code, verbose=self.verbose)
                page.wait_for_timeout(1500)

                html = page.content()
                product = self._parse_product_from_html(html, url)
                product = enrich_from_browser(product, page)
                page.close()

                if product and (product.price or product.asin):
                    products.append(product)
                    # Cache successful scrape for future use
                    if self.cache:
                        self.cache.put(url, html)

            except Exception as e:
                if self.verbose:
                    log.warning("Error processing search result %s: %s", url, e)
                continue

        return products

    def scrape_search(self, query: str) -> list[Product]:
        """Scrape a search query and return Product objects.

        This is the main public interface for searching Amazon products.
        It returns a list of Product objects with enriched data.
        """
        if self.verbose:
            log.info("Running search for: %s", query)

        return self._run_search(query)

    def scrape_product(self, url: str) -> Product:
        """Scrape a single product URL and return a Product object.

        This method is ideal for extracting detailed information from a specific
        Amazon product page, including all available product details and enriched
        browser data.
        """
        if self.verbose:
            log.info("Running product scrape for: %s", url)

        # Try to use cached HTML first if available
        if self.cache:
            cached_html = self.cache.get(url)
            if cached_html is not None:
                product = self._parse_product_from_html(cached_html, url)
                if self.verbose:
                    log.info("Using cached HTML for %s", url)
                return product

        # If not cached, scrape the URL
        page = self.session.navigate_with_retry(url)
        self.session.set_zip_code(page, zip_code=self.zip_code, verbose=self.verbose)
        page.wait_for_timeout(1500)

        html = page.content()
        product = self._parse_product_from_html(html, url)
        product = enrich_from_browser(product, page)
        page.close()

        # Cache successful scrape for future use
        if self.cache:
            self.cache.put(url, html)

        return product

    def _parse_product_from_html(self, html: str, url: str) -> Product:
        """Parse product HTML into a Product object.

        This method handles the actual parsing of HTML content and enriches the
        Product with browser-based data for more accurate extraction.
        """
        try:
            return parse_search_card(html, self.session.domain, self.verbose)
        except Exception as e:
            if self.verbose:
                log.warning("Failed to parse product from HTML: %s", e)
            # Re-raise with more context about the error
            raise ParseError(url, f"Failed to parse product: {e}", "parse") from e