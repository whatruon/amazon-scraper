from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from .config import LOAD_MORE_REVIEWS_SELECTORS, SEE_ALL_REVIEWS_SELECTORS
from .masking import mask_proxy_credentials

log = logging.getLogger(__name__)


def scrape_reviews(page: Page, max_reviews: int = 100) -> list[dict]:
    """
    Extract reviews from Amazon product page.

    Args:
        page: Playwright Page object
        max_reviews: Maximum number of reviews to extract

    Returns:
        List of dictionaries containing review data:
        - text: Review text
        - rating: Rating as string (e.g., "5.0 out of 5 stars")
        - date: Review date
        - verified: Whether review is verified purchase
        - helpful_votes: Number of helpful votes
    """
    reviews: list[dict] = []
    try:
        # Navigate to review section if needed
        _ensure_reviews_loaded(page)

        seen_reviews: set[tuple] = set()
        no_progress_rounds = 0
        while len(reviews) < max_reviews:
            before = len(reviews)
            soup = BeautifulSoup(page.content(), "lxml")
            for element in soup.select('[data-hook="review"]'):
                if len(reviews) >= max_reviews:
                    break
                review_data = _extract_review_from_element(element)
                if not review_data:
                    continue
                dedup_key = (review_data.get('text', ''), review_data.get('date', ''))
                if dedup_key not in seen_reviews:
                    seen_reviews.add(dedup_key)
                    reviews.append(review_data)

            if len(reviews) == before:
                no_progress_rounds += 1
            else:
                no_progress_rounds = 0

            if no_progress_rounds >= 3:
                log.warning(
                    "Review pagination stalled after %d round(s) with no new reviews; "
                    "stopping at %d review(s)",
                    no_progress_rounds,
                    len(reviews),
                )
                break

            # Stop once we have enough reviews or there is no "load more" control.
            if len(reviews) >= max_reviews or not _load_more_reviews(page):
                break

    except Exception as e:
        log.warning("Error scraping reviews: %s", mask_proxy_credentials(str(e)))

    return reviews[:max_reviews]


def _ensure_reviews_loaded(page: Page, timeout: int = 5000) -> None:
    """Navigate to the full review list, if a "see all reviews" link is present."""
    for selector in SEE_ALL_REVIEWS_SELECTORS:
        try:
            element = page.query_selector(selector)
            if element and element.is_visible():
                element.click()
                _wait_for_review_load(page, timeout)
                return
        except Exception as e:
            log.debug("See-all-reviews control unavailable for %s: %s", selector, mask_proxy_credentials(str(e)))


def _load_more_reviews(page: Page, timeout: int = 5000) -> bool:
    """Click a "load more / next page" control for reviews. Returns True if clicked.

    A load-state timeout after a successful click is not a failure — the click
    already happened — so it is only logged at DEBUG level.
    """
    for selector in LOAD_MORE_REVIEWS_SELECTORS:
        try:
            element = page.query_selector(selector)
            if element and element.is_visible():
                element.click()
                _wait_for_review_load(page, timeout)
                return True
        except Exception as e:
            log.debug("Load-more control unavailable for %s: %s", selector, mask_proxy_credentials(str(e)))
    return False


def _wait_for_review_load(page: Page, timeout: int) -> None:
    """Best-effort wait for the page to settle after clicking a review control."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception as e:
        log.debug("Review load-state wait timed out: %s", mask_proxy_credentials(str(e)))


def _extract_review_from_element(element) -> dict | None:
    """Extract review data from a single review element."""
    try:
        review_data = {}

        # Extract review text
        text_el = element.select_one('[data-hook="review-body"] span')
        if not text_el:
            text_el = element.select_one('[data-hook="review-body"]')
        review_data['text'] = text_el.get_text(strip=True) if text_el else None

        # Extract rating
        rating_el = element.select_one('[data-hook="review-star-rating"]')
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            rating_match = re.search(r'([\d.]+)\s*out\s*of\s*5', rating_text)
            if rating_match:
                review_data['rating'] = rating_match.group(1)
            else:
                review_data['rating'] = rating_text

        # Extract date
        date_el = element.select_one('[data-hook="review-date"]')
        if date_el:
            date = date_el.get_text(strip=True)
            if date:
                # Clean up date text (remove "Reviewed in ... on " prefix)
                date = re.sub(r'^.*?\b(?:on|am)\b\s*', '', date, flags=re.IGNORECASE)
            review_data['date'] = date

        # Extract verified badge
        verified_el = element.select_one('[data-hook="avp-badge"]')
        review_data['verified'] = bool(verified_el and 'Verified Purchase' in verified_el.get_text())

        # Extract helpful votes
        review_data['helpful_votes'] = _extract_helpful_votes(element)

    except Exception as e:
        log.warning("Failed to extract review from element: %s", mask_proxy_credentials(str(e)))
        return None

    return review_data


def _extract_helpful_votes(element) -> int | None:
    """Extract number of helpful votes from review element."""
    helpful_el = element.select_one('[data-hook="helpful-vote-statement"]')
    if not helpful_el:
        return None

    helpful_text = helpful_el.get_text(strip=True)

    # Try to extract numeric value
    helpful_match = re.search(
        r'(\d+)\s*(?:person|people)\s*found\s+this\s+helpful', helpful_text, re.IGNORECASE,
    )
    if helpful_match:
        return int(helpful_match.group(1))

    # Try to extract word form (One, Two, Three, etc.)
    word_match = re.search(
        r'(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\s*(?:person|people)\s*'
        r'found\s+this\s+helpful',
        helpful_text, re.IGNORECASE,
    )
    if word_match:
        number_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        }
        return number_words.get(word_match.group(1).lower(), 1)

    return None
