from __future__ import annotations

import logging
import time
from typing import Optional

from .browser import BrowserSession

log = logging.getLogger(__name__)


def search_amazon(
    session: BrowserSession,
    query: str,
    max_results: int = 5,
    timeout: int = 15000,
    wait: int = 0,
    verbose: bool = False,
) -> list[str]:
    """
    Search Amazon for a query and return product URLs.

    Args:
        session: BrowserSession with anti-detection features configured
        query: Search term to use
        max_results: Maximum number of product URLs to return
        timeout: Navigation timeout in milliseconds
        wait: Extra wait time after page load in milliseconds
        verbose: Enable verbose logging

    Returns:
        List of product URLs from search results
    """
    from .parser import parse_search_results

    # Build search URL
    search_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}&i=stripbooks"
    if verbose:
        log.info("Search URL: %s", search_url)

    page = session.new_page()
    results: list[str] = []
    pages_fetched = 0
    max_pages = 3  # Safety limit to avoid infinite pagination

    try:
        while len(results) < max_results and pages_fetched < max_pages:
            if pages_fetched > 0:
                # Construct pagination URL
                page_num = pages_fetched + 1
                search_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}&i=stripbooks&page={page_num}"

            page = session.new_page()
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)

                # Check for CAPTCHA
                captcha_btn = page.query_selector("button[alt='Continue shopping']")
                if captcha_btn:
                    if verbose:
                        log.info("CAPTCHA detected during search, clicking through...")
                    captcha_btn.click()
                    try:
                        page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
                    except Exception:
                        pass

                if wait:
                    page.wait_for_timeout(wait)

                html = page.content()
                page_urls = parse_search_results(html)

                if not page_urls:
                    if verbose:
                        log.warning("No results found on page %d", pages_fetched + 1)
                    break

                for url in page_urls:
                    if url not in results:
                        results.append(url)
                        if len(results) >= max_results:
                            break

                if verbose:
                    log.info(
                        "Page %d: found %d URLs (total: %d/%d)",
                        pages_fetched + 1,
                        len(page_urls),
                        len(results),
                        max_results,
                    )

                pages_fetched += 1

            finally:
                page.close()

            # Small delay between pages
            time.sleep(1)

    except Exception as e:
        if verbose:
            log.warning("Search error: %s", e)

    return results[:max_results]