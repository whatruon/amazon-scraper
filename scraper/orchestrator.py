from __future__ import annotations

import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from .browser import BrowserSession
from .config import (
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MAX_REVIEWS,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
)
from .errors import ParseError, ScrapeError
from .models import Product
from .parser import enrich_from_browser, parse_product
from .price_tracker import track_price
from .review import scrape_reviews
from .search import search_amazon as search_amazon_func
from .seller import scrape_seller_info

log = logging.getLogger(__name__)

# Settle time after navigation before reading the page content.
POST_NAV_SETTLE_MS = 1500

# CSPRNG for retry-backoff jitter (avoids the non-crypto `random` module).
_rng = secrets.SystemRandom()


class ScrapeOrchestrator:
    """Orchestration layer for scraping products from Amazon.

    Consolidates the business logic from cli.py into a reusable class that can be
    used both from the CLI and from the Apify actor.
    """

    def __init__(
        self,
        session: BrowserSession,
        cache=None,
        zip_code: str = "90035",
        max_results: int = DEFAULT_MAX_RESULTS,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_reviews: int = DEFAULT_MAX_REVIEWS,
        retries: int = DEFAULT_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
        wait: int = 0,
        verbose: bool = False,
    ) -> None:
        self.session = session
        self.cache = cache
        self.zip_code = zip_code
        self.max_results = max_results
        self.max_pages = max_pages
        self.max_reviews = max(0, max_reviews)
        self.retries = max(1, retries)
        self.timeout = timeout
        self.wait = wait
        self.verbose = verbose

    def scrape_search(
        self,
        query: str,
        *,
        on_product: Callable[[Product], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[Product]:
        """Run a search query, scraping each result URL.

        *on_product* is invoked for each successfully scraped Product (useful for
        streaming results to a dataset as they arrive). *should_stop* lets the
        caller request a graceful stop between results.
        """
        if self.verbose:
            log.info("Running search for: %s", query)
        results = search_amazon_func(
            self.session,
            query,
            max_results=self.max_results,
            max_pages=self.max_pages,
            timeout=self.timeout,
            wait=self.wait,
            verbose=self.verbose,
        )

        products: list[Product] = []
        for result in results:
            if should_stop and should_stop():
                break
            try:
                product = self._scrape_single_url(result.url, should_stop=should_stop)
            except ScrapeError as e:
                # A single bad URL must not abort the whole search.
                log.warning("Skipping %s: %s", result.url, e)
                continue
            if product:
                products.append(product)
                if on_product:
                    on_product(product)
        if self.verbose:
            log.info("Scraped %d products", len(products))
        return products

    def scrape_product(self, url: str, *, should_stop: Callable[[], bool] | None = None) -> Product | None:
        """Scrape a single product URL and return a Product object.

        Returns None only when *should_stop* requested a graceful stop. Raises
        ScrapeError (navigation/parse) when the product could not be scraped
        after all retries.
        """
        if self.verbose:
            log.info("Running product scrape for: %s", url)

        return self._scrape_single_url(url, should_stop=should_stop)

    def _scrape_single_url(
        self,
        url: str,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> Product | None:
        """Scrape a single URL and return Product, or None when stopped.

        Returns None only when *should_stop* fired before the scrape could
        complete. Any navigation/parse failure that survives all retries is
        raised as a ScrapeError subclass.
        """
        if self.cache:
            cached_html = self.cache.get(url)
            if cached_html is not None:
                product = self._parse_product_from_html(cached_html, url)
                product = self._enrich_from_html(product, cached_html)
                if product and product.price and product.asin:
                    product.from_cache = True
                    cached_ts = self.cache.cached_at(url)
                    if cached_ts:
                        product.scraped_at = datetime.fromtimestamp(cached_ts, UTC).isoformat()
                    if self.max_reviews > 0:
                        # Reviews require live navigation, so a cached product
                        # gets them refreshed in a separate throwaway page.
                        self._scrape_reviews_for_cached(url, product)
                    if self.verbose:
                        log.info("Using cached HTML for %s", url)
                    return product

        last_exc: Exception | None = None
        for attempt in range(self.retries):
            if should_stop and should_stop():
                return None
            page = None
            try:
                page = self.session.navigate_with_retry(
                    url,
                    retries=1,
                    timeout=self.timeout,
                    wait=self.wait,
                    verbose=self.verbose,
                )
                self.session.set_zip_code(page, zip_code=self.zip_code, verbose=self.verbose)
                page.wait_for_timeout(POST_NAV_SETTLE_MS)

                html = page.content()
                product = self._parse_product_from_html(html, url)
                product = enrich_from_browser(product, page)
                product = self._enrich_from_html(product, html)

                if product and product.price and product.asin:
                    if self.max_reviews > 0:
                        # Reviews are scraped last: scraping them navigates the
                        # page to the reviews section, which would invalidate
                        # the product-page HTML captured above.
                        product.reviews = scrape_reviews(page, self.max_reviews)
                    if self.cache:
                        self.cache.put(url, html)
                    return product
                last_exc = ParseError(url, reason="Failed to extract price or ASIN from page")
                if self.verbose:
                    log.warning("Attempt %d/%d: missing price/asin for %s", attempt + 1, self.retries, url)
            except ScrapeError as e:
                last_exc = e
                if self.verbose:
                    log.warning("Error processing %s (attempt %d/%d): %s", url, attempt + 1, self.retries, e)
            except Exception as e:
                last_exc = e
                if self.verbose:
                    log.warning("Error processing %s (attempt %d/%d): %s", url, attempt + 1, self.retries, e)
            finally:
                if page:
                    with contextlib.suppress(Exception):
                        page.close()

            if attempt < self.retries - 1:
                self._sleep_interruptibly(2**attempt + _rng.uniform(0, 1), should_stop)

        if last_exc is not None:
            raise last_exc
        return None

    def _scrape_reviews_for_cached(self, url: str, product: Product) -> None:
        """Best-effort refresh of reviews for a product served from cache.

        A failure here is never fatal: the cached product is still returned,
        just without fresh reviews.
        """
        page = None
        try:
            page = self.session.navigate_with_retry(
                url,
                retries=1,
                timeout=self.timeout,
                wait=self.wait,
                verbose=self.verbose,
            )
            product.reviews = scrape_reviews(page, self.max_reviews)
        except Exception as e:
            log.warning("Could not scrape reviews for cached product %s: %s", url, e)
        finally:
            if page:
                with contextlib.suppress(Exception):
                    page.close()

    def _parse_product_from_html(self, html: str, url: str) -> Product:
        """Parse product HTML into a Product object."""
        return parse_product(html, url)

    def _enrich_from_html(self, product: Product, html: str) -> Product:
        """Attach price/deal and seller information parsed from the page HTML.

        Works without a live browser page, so cached products get the same
        enrichment. Reviews are not attached here because they require live
        page navigation.
        """
        soup = BeautifulSoup(html, "lxml")
        price_info = track_price(soup=soup)
        product.original_price = price_info.get("original_price")
        product.discount_percentage = price_info.get("discount_percentage")
        product.deal_type = price_info.get("deal_type")
        product.is_on_sale = price_info.get("is_on_sale", False)
        product.savings_amount = price_info.get("savings_amount")

        seller = scrape_seller_info(soup=soup)
        product.seller_name = seller.get("seller_name")
        product.fulfilled_by_amazon = seller.get("fulfilled_by_amazon", False)
        product.seller_rating = seller.get("seller_rating")
        product.seller_rating_count = seller.get("seller_rating_count")
        product.buybox_owner = seller.get("buybox_owner", False)
        product.ships_from = seller.get("ships_from")
        return product

    def _sleep_interruptibly(
        self,
        seconds: float,
        should_stop: Callable[[], bool] | None,
    ) -> None:
        """Sleep in short slices so a graceful stop can break out early."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if should_stop and should_stop():
                return
            time.sleep(min(0.25, deadline - time.monotonic()))
