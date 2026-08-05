from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from .config import (
    FBA_SELECTORS,
    SELLER_RATING_SELECTORS,
    SELLER_SELECTORS,
    SHIPS_FROM_SELECTORS,
)

log = logging.getLogger(__name__)

# Shared keywords for FBA detection. Deliberately narrow: only explicit
# fulfillment phrases count, so generic page text (e.g. "free shipping",
# "Prime") does not produce false positives.
_FBA_KEYWORDS = {
    'fulfilled by amazon',
    'ships from amazon',
    'shipped from amazon',
}

# Page-wide FBA phrase search. Compiled once and matched against the Buy Box
# container only (see ``_is_fulfilled_by_amazon``) so mentions in reviews,
# Q&A or the footer do not produce false positives.
_FBA_TEXT_RE = re.compile(r'(sold by amazon|ships from amazon|fulfilled by amazon)', re.I)

_NO_SOURCE_MSG = "scrape_seller_info() requires a page or a soup"


def scrape_seller_info(page: Page | None = None, soup: BeautifulSoup | None = None) -> dict:
    """
    Extract seller information from Amazon product page.

    Args:
        page: Playwright Page object. Required when *soup* is not provided.
        soup: Pre-parsed product-page HTML. Required when *page* is not provided.

    Returns:
        Dictionary containing seller information:
        - seller_name: Name of the seller
        - fulfilled_by_amazon: Whether product is fulfilled by Amazon
        - seller_rating: Seller rating (if available)
        - seller_rating_count: Number of seller ratings
        - buybox_owner: Whether seller owns the Buy Box
        - ships_from: Location ships from
    """
    if soup is None:
        if page is None:
            raise ValueError(_NO_SOURCE_MSG)
        soup = BeautifulSoup(page.content(), "lxml")

    seller_rating, seller_rating_count = _extract_seller_rating(soup)
    return {
        'seller_name': _extract_seller_name(soup),
        'fulfilled_by_amazon': _is_fulfilled_by_amazon(soup),
        'seller_rating': seller_rating,
        'seller_rating_count': seller_rating_count,
        'buybox_owner': _is_buybox_owner(soup),
        'ships_from': _extract_ships_from(soup),
    }


def _extract_seller_name(soup: BeautifulSoup) -> str | None:
    """Extract seller/merchant name."""
    for selector in SELLER_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            # Clean up common prefixes
            text = re.sub(r'^(?:Visit the|Sold by:?\s*)', '', text, flags=re.IGNORECASE)
            text = text.strip()
            # Avoid generic text like "See more"
            if text and len(text) > 1 and not text.lower().startswith(('see', 'visit', 'more')):
                return text
    # Alternative: look for "Sold by:" text
    for element in soup.find_all(string=re.compile(r'Sold by:', re.I)):
        parent = element.parent
        if parent:
            seller_el = parent.find_next(['span', 'a'])
            if seller_el:
                seller_text = seller_el.get_text(strip=True)
                if seller_text and len(seller_text) > 1:
                    return seller_text

    return None


def _is_fulfilled_by_amazon(soup: BeautifulSoup) -> bool:
    """Check if product is fulfilled by Amazon.

    Only explicit fulfillment phrases count; a Prime badge alone is not
    proof of FBA (merchant-fulfilled Prime listings exist).
    """
    # Check specific FBA elements
    for selector in FBA_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True).lower()
            if any(keyword in text for keyword in _FBA_KEYWORDS):
                return True

    # Check for "Sold by Amazon" / "Ships from Amazon" / "Fulfilled by Amazon"
    # inside the Buy Box only. Mentions elsewhere (reviews, Q&A, footer) are
    # unrelated to this listing's fulfillment. If no buybox can be located we
    # fall back to the whole page so existing behavior is preserved.
    buybox = _find_buybox(soup)
    scope = buybox if buybox is not None else soup
    return bool(scope.find_all(string=_FBA_TEXT_RE))


def _extract_seller_rating(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract seller rating and rating count."""
    rating_text = None
    rating_count = None

    for selector in SELLER_RATING_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text:
                # Look for rating pattern like "4.5 out of 5 stars"
                rating_match = re.search(r'([\d.]+)\s*out\s*of\s*5', text)
                if rating_match:
                    rating_text = rating_match.group(1)
                # Look for rating count pattern like "1,234 ratings"
                count_match = re.search(r'([\d,]+)\s*(?:ratings?|reviews?)', text, re.I)
                if count_match:
                    rating_count = count_match.group(1).replace(',', '')
                if rating_text and rating_count:
                    break

    # Alternative: look for seller stars in feedback section
    feedback_section = soup.select_one('#feedbackSummaryTable, .feedbackDetailStars')
    if feedback_section:
        rating_el = feedback_section.select_one('.avgRating, .stars')
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            # Extract numeric value
            numeric_match = re.search(r'([\d.]+)', rating_text)
            if numeric_match:
                rating_text = numeric_match.group(1)

    return rating_text, rating_count


_BUYBOX_CONTAINERS = (
    "#buybox",
    "#BuyBox",
    "#buybox-see-all-buying-choices",
    "#addToCart_feature_div",
    "#corePrice_feature_div",
    "#corePriceDisplay_desktop_feature_div",
    "#centerCol",
)

# Matches a buybox "Sold by" statement and captures the seller name it names,
# e.g. "Sold by Acme Inc", "Sold by: Amazon".
_SOLD_BY_RE = re.compile(r'^\s*sold\s+by\b\s*:?\s*(.*)$', re.I)

# Seller labels that refer to Amazon itself; naming Amazon in the buybox means
# Amazon owns the Buy Box regardless of the extracted seller name.
_AMAZON_SELLER_NAMES = {'amazon', 'amazon.com', 'amazon.com, inc.'}


def _find_buybox(soup: BeautifulSoup) -> BeautifulSoup | None:
    """Return the first Buy Box container element, or None if none is found."""
    for selector in _BUYBOX_CONTAINERS:
        buybox = soup.select_one(selector)
        if buybox:
            return buybox
    return None


def _normalize_seller_name(name: str) -> str:
    """Normalize a seller label for comparison.

    Strips common prefixes ("Visit the", "Brand:", "Sold by:"), trailing
    punctuation and whitespace, and lowercases the result.
    """
    text = re.sub(
        r'^(?:visit\s+the|brand:?\s*|sold\s+by:?\s*)',
        '',
        name.strip(),
        flags=re.IGNORECASE,
    )
    text = re.sub(r'[\s.,!?;:]+$', '', text)
    return text.strip().lower()


def _is_amazon_seller(name: str) -> bool:
    """Return True if a seller label refers to Amazon itself."""
    return _normalize_seller_name(name) in _AMAZON_SELLER_NAMES


def _extract_buybox_sold_by(buybox: BeautifulSoup) -> str | None:
    """Extract the seller named by a "Sold by" statement inside the buybox.

    Handles the inline form ("Sold by: Acme Inc") as well as the labeled form
    ("Sold by" label element followed by a separate seller link).
    """
    for el in buybox.select('a, span'):
        match = _SOLD_BY_RE.match(el.get_text(' ', strip=True))
        if match and match.group(1):
            return match.group(1).strip()

    for node in buybox.find_all(string=_SOLD_BY_RE):
        parent = node.parent
        if parent is None:
            continue
        match = _SOLD_BY_RE.match(parent.get_text(' ', strip=True))
        if match and match.group(1):
            return match.group(1).strip()
        seller_el = parent.find_next(['a', 'span'])
        if seller_el is not None:
            seller = seller_el.get_text(' ', strip=True)
            if seller:
                return seller

    return None


def _is_buybox_owner(soup: BeautifulSoup) -> bool:
    """Check if the seller owns the Buy Box.

    Ownership is decided by the buybox's "Sold by" statement: it must name the
    extracted seller (case-insensitive) or Amazon itself. "Fulfilled by
    Amazon" / "Ships from Amazon" alone do not grant ownership, and a buybox
    that explicitly names a different seller means the seller does not own it.
    """
    buybox = _find_buybox(soup)
    if buybox is not None:
        buybox_seller = _extract_buybox_sold_by(buybox)
        if buybox_seller:
            if _is_amazon_seller(buybox_seller):
                return True
            seller_name = _extract_seller_name(soup)
            # The buybox explicitly names a different seller -> not the owner.
            return bool(
                seller_name
                and _normalize_seller_name(buybox_seller) == _normalize_seller_name(seller_name)
            )

    # Fallback: a prominent seller-name mention inside the buybox.
    seller_name = _extract_seller_name(soup)
    return bool(
        seller_name
        and buybox is not None
        and seller_name.lower() in buybox.get_text(' ', strip=True).lower()
    )


def _extract_ships_from(soup: BeautifulSoup) -> str | None:
    """Extract where the item ships from."""
    for selector in SHIPS_FROM_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) > 3:
                # Clean up common prefixes
                text = re.sub(r'^(?:ships from|ships from:?\s*)', '', text, flags=re.IGNORECASE)
                text = text.strip()
                if text:
                    return text

    # Look for "Ships from" text pattern inside the Buy Box only. Mentions in
    # reviews, Q&A or the footer are unrelated to this listing. If no buybox is
    # found we fall back to the whole page so existing behavior is preserved.
    buybox = _find_buybox(soup)
    scope = buybox if buybox is not None else soup
    for element in scope.find_all(string=re.compile(r'Ships from:', re.I)):
        parent = element.parent
        if parent:
            ships_text = parent.get_text(strip=True)
            ships_text = re.sub(r'^.*?Ships from:\s*', '', ships_text, flags=re.IGNORECASE)
            ships_text = ships_text.strip()
            if ships_text and len(ships_text) > 2:
                return ships_text

    return None
