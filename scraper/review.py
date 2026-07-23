from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Page

from .models import Product
from .config import SEE_ALL_REVIEWS_SELECTORS, LOAD_MORE_REVIEWS_SELECTORS

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
    reviews = []

    try:
        for selector in SEE_ALL_REVIEWS_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    element.click()
                    page.wait_for_load_state("networkidle", timeout=5000)
                    break
            except Exception:
                continue

        # Load more reviews if needed
        seen_reviews = set()
        while len(reviews) < max_reviews:
            # Get page content
            content = page.content()
            soup = BeautifulSoup(content, "lxml")

            # Extract reviews from current page
            review_elements = soup.select('[data-hook="review"]')
            for element in review_elements:
                if len(reviews) >= max_reviews:
                    break

                review_data = _extract_review_from_element(element)
                if review_data:
                    dedup_key = (review_data.get('text', ''), review_data.get('date', ''))
                    if dedup_key not in seen_reviews:
                        seen_reviews.add(dedup_key)
                        reviews.append(review_data)

            # Try to load more reviews if we need more
            if len(reviews) < max_reviews:
                load_more_clicked = False
                for selector in LOAD_MORE_REVIEWS_SELECTORS:
                    try:
                        element = page.query_selector(selector)
                        if element and element.is_visible():
                            element.click()
                            page.wait_for_load_state("networkidle", timeout=5000)
                            load_more_clicked = True
                            break
                    except Exception:
                        continue

                if not load_more_clicked:
                    # No more reviews to load
                    break
            else:
                break

    except Exception as e:
        log.warning("Error scraping reviews: %s", e)

    return reviews[:max_reviews]


def _extract_review_from_element(element: Tag) -> dict | None:
    """Extract review data from a single review element."""
    try:
        # Extract review text
        text_el = element.select_one('[data-hook="review-body"] span')
        if not text_el:
            text_el = element.select_one('[data-hook="review-body"]')
        text = text_el.get_text(strip=True) if text_el else None

        # Extract rating
        rating_el = element.select_one('[data-hook="review-star-rating"]')
        rating = None
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            # Extract rating like "4.0 out of 5 stars"
            rating_match = re.search(r'([\d.]+)\s*out\s*of\s*5', rating_text)
            if rating_match:
                rating = rating_match.group(1)
            else:
                rating = rating_text

        # Extract date
        date_el = element.select_one('[data-hook="review-date"]')
        date = date_el.get_text(strip=True) if date_el else None
        if date:
            # Clean up date text (remove "Reviewed in ... on " prefix)
            date = re.sub(r'^.*?\b(?:on|am)\b\s*', '', date, flags=re.IGNORECASE)

        # Extract verified badge
        verified_el = element.select_one('[data-hook="avp-badge"]')
        verified = bool(verified_el and 'Verified Purchase' in verified_el.get_text())

        # Extract helpful votes
        NUMBER_WORDS = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        }
        helpful_el = element.select_one('[data-hook="helpful-vote-statement"]')
        helpful_votes = None
        if helpful_el:
            helpful_text = helpful_el.get_text(strip=True)
            helpful_match = re.search(r'(\d+)\s*people?\s*found\s+this\s+helpful', helpful_text, re.IGNORECASE)
            if helpful_match:
                helpful_votes = int(helpful_match.group(1))
            else:
                word_match = re.search(r'(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\s*people?\s*found\s+this\s+helpful', helpful_text, re.IGNORECASE)
                if word_match:
                    helpful_votes = NUMBER_WORDS.get(word_match.group(1).lower(), 1)

        return {
            'text': text,
            'rating': rating,
            'date': date,
            'verified': verified,
            'helpful_votes': helpful_votes
        }

    except Exception as e:
        log.warning("Failed to extract review from element: %s", e)
        return None