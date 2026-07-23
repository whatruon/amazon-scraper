from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import quote_plus

from .browser import BrowserSession
from .models import SearchResult
from .parser import parse_search_card, parse_search_results

log = logging.getLogger(__name__)


def _build_search_url(domain: str, query: str, page_num: int | None = None) -> str:
    base = f"https://{domain}/s?k={quote_plus(query)}"
    if page_num is not None:
        base += f"&page={page_num}"
    return base


def search_amazon(
    session: BrowserSession,
    query: str,
    max_results: int = 5,
    timeout: int = 15000,
    wait: int = 0,
    verbose: bool = False,
    max_pages: int = 3,
) -> list[SearchResult]:
    """
    Search Amazon for a query and return structured search results.

    Args:
        session: BrowserSession with anti-detection features configured
        query: Search term to use
        max_results: Maximum number of results to return
        timeout: Navigation timeout in milliseconds
        wait: Extra wait time after page load in milliseconds
        verbose: Enable verbose logging
        max_pages: Maximum number of pages to fetch

    Returns:
        List of SearchResult objects from search results
    """

    # Build search URL
    search_url = _build_search_url(session.domain, query)
    if verbose:
        log.info("Search URL: %s", search_url)

    results: list[SearchResult] = []
    pages_fetched = 0

    try:
        while len(results) < max_results and pages_fetched < max_pages:
            if pages_fetched > 0:
                # Construct pagination URL
                page_num = pages_fetched + 1
                search_url = _build_search_url(session.domain, query, page_num)

            page = session.new_page()
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)

                # Check for CAPTCHA
                captcha_btn = page.query_selector("button[alt='Continue shopping']")
                if captcha_btn:
                    log.warning("CAPTCHA detected during search")
                    captcha_btn.click()
                    try:
                        page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
                    except Exception:
                        log.warning("Search CAPTCHA click did not resolve to results")

                if wait:
                    page.wait_for_timeout(wait)

                html = page.content()
                page_results = parse_search_card(html, session.domain)

                if not page_results:
                    if verbose:
                        log.warning("No results found on page %d", pages_fetched + 1)
                    break

                existing_urls = {r.url for r in results}
                for result in page_results:
                    if result.url not in existing_urls:
                        results.append(result)
                        existing_urls.add(result.url)
                        if len(results) >= max_results:
                            break

                if verbose:
                    log.info(
                        "Page %d: found %d results (total: %d/%d)",
                        pages_fetched + 1,
                        len(page_results),
                        len(results),
                        max_results,
                    )

                pages_fetched += 1

            finally:
                page.close()

            # Small delay between pages
            time.sleep(1)

    except Exception as e:
        log.warning("Search error: %s", e)

    return results[:max_results]
