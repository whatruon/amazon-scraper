from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus

from .browser import BrowserSession
from .errors import CaptchaError
from .masking import mask_proxy_credentials
from .models import SearchResult
from .parser import parse_search_card

log = logging.getLogger(__name__)


def _build_search_url(domain: str, query: str, page_num: int | None = None) -> str:
    """Build the search URL for Amazon with optional pagination."""
    base = f"https://{domain}/s?k={quote_plus(query)}"
    if page_num is not None:
        base += f"&page={page_num}"
    return base


def _extract_search_results(html: str, domain: str) -> list[SearchResult]:
    """Parse search results HTML and return structured results, deduplicated."""
    return parse_search_card(html, domain)


def _should_stop_search(results: list[SearchResult], max_results: int, pages_fetched: int, max_pages: int) -> bool:
    """Determine if search should continue based on results count and page limits."""
    return len(results) < max_results and pages_fetched < max_pages


def _fetch_search_page(
    session: BrowserSession,
    search_url: str,
    timeout: int,
    wait: int,
    verbose: bool,
    retries: int = 2,
) -> str | None:
    """Fetch a single search page and return HTML content, or None on failure.

    Retries each attempt with a fresh page and exponential backoff. A
    CaptchaError raised on the last attempt is re-raised so callers can react;
    any other failure yields None.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        page = None
        try:
            page = session.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout)

            # Check for CAPTCHA and attempt to bypass
            _handle_captcha_if_present(
                page, search_url, verbose, mask=mask_proxy_credentials,
            )

            if wait:
                page.wait_for_timeout(wait)

            return page.content()

        except Exception as e:
            last_exc = e
            log.warning(
                "Failed to fetch search page (attempt %d/%d): %s",
                attempt + 1,
                retries,
                mask_proxy_credentials(str(e)),
            )
            if attempt < retries - 1:
                time.sleep(2**attempt + random.uniform(0, 1))  # noqa: S311
        finally:
            # Each attempt owns a fresh page; close it on both the success and
            # failure paths so no browser pages leak.
            if page:
                page.close()

    if isinstance(last_exc, CaptchaError):
        raise last_exc
    return None


def _handle_captcha_if_present(page, url: str, verbose: bool, mask=lambda s: s) -> bool:
    """Check for CAPTCHA and click through if detected.

    Returns True when a CAPTCHA was detected and resolved to search results,
    False when no CAPTCHA was present. Raises CaptchaError when a CAPTCHA was
    detected but could not be resolved to search results.
    """
    captcha_btn = page.query_selector("button[alt='Continue shopping']")
    if captcha_btn:
        log.warning("CAPTCHA detected during search")
        if verbose:
            log.info("CAPTCHA detected, clicking through...")
        captcha_btn.click()
        try:
            page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
        except Exception as e:
            reason = mask(str(e))
            log.warning("Search CAPTCHA click did not resolve to results: %s", reason)
            raise CaptchaError(url, reason) from e
        return True
    return False


def search_amazon(
    session: BrowserSession,
    query: str,
    max_results: int = 5,
    timeout: int = 15000,
    wait: int = 0,
    verbose: bool = False,
    max_pages: int = 3,
    retries: int = 2,
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
        retries: Number of attempts per search page fetch

    Returns:
        List of SearchResult objects from search results
    """
    search_url = _build_search_url(session.domain, query)
    if verbose:
        log.info("Search URL: %s", search_url)

    results: list[SearchResult] = []
    pages_fetched = 0

    while _should_stop_search(results, max_results, pages_fetched, max_pages):
        if pages_fetched > 0:
            page_num = pages_fetched + 1
            search_url = _build_search_url(session.domain, query, page_num)

        html = _fetch_search_page(session, search_url, timeout, wait, verbose)
        if not html:
            log.warning("No HTML content retrieved for page %d", pages_fetched + 1)
            break

        page_results = _extract_search_results(html, session.domain)
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

        # Small delay between pages to avoid rate limiting — only when
        # another page will actually be fetched.
        if _should_stop_search(results, max_results, pages_fetched, max_pages):
            time.sleep(1)

    return results[:max_results]
