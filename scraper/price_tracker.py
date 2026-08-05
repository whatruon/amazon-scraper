from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from .config import COUPON_SELECTORS, DEAL_SELECTORS, ORIGINAL_PRICE_SELECTORS
from .parser import extract_price

log = logging.getLogger(__name__)


class TrackPriceError(ValueError):
    """Raised when track_price() cannot determine what to parse."""


# Currency symbols Amazon renders prices with, matched as a character class.
_CURRENCY_SYMBOL = r"[$£€¥₹]"

# Price-like substrings for fallback extraction: prefix symbols (with optional
# space, incl. multi-char like 'CDN$') and EU-style trailing symbols.
_AMOUNT_RE = (
    r"(?:US\$|CDN\$|MX\$|R\$|A\$|C\$|S\$|HK\$|₹|€|£|¥|\$)\s*\d+(?:[.,]\d{1,3})*(?:[.,]\d{1,2})?"
    r"|\d+(?:\.\d{3})*(?:,\d{1,2})?\s*(?:€|£|¥|₹|\$)"
)


def track_price(page: Page | None = None, soup: BeautifulSoup | None = None) -> dict:
    """
    Extract price and deal information from Amazon product page.

    Args:
        page: Playwright Page object. Required when *soup* is not provided.
        soup: Pre-parsed product-page HTML. Required when *page* is not provided.

    Returns:
        Dictionary containing price information:
        - current_price: Current price as string (e.g., "$29.99")
        - original_price: Original price if on sale (e.g., "$39.99")
        - discount_percentage: Discount percentage if on sale
        - deal_type: Type of deal (e.g., "Lightning Deal", "Deal of the Day")
        - is_on_sale: Boolean indicating if product is on sale
        - savings_amount: Amount saved if on sale
    """
    if soup is None:
        if page is None:
            msg = "track_price() requires a page or a soup"
            raise TrackPriceError(msg)
        soup = BeautifulSoup(page.content(), "lxml")

    # Extract current price using the standardized parser logic (reuses
    # PRICE_SELECTORS, with a browser-JS fallback when the page has no static HTML).
    price_info = {
        'current_price': extract_price(soup, page),
        'original_price': None,
        'discount_percentage': None,
        'deal_type': None,
        'is_on_sale': False,
        'savings_amount': None,
    }

    price_info['original_price'] = _extract_original_price(soup)
    price_info.update(_extract_deal_info(soup))
    _apply_discount(price_info)

    return price_info


def _to_amount(text: str | None) -> float | None:
    """Parse a price string (e.g. '$29.99', '29,99', '1.234,56') into a float.

    Handles both US formats (dot decimal / comma thousands) and EU formats
    (comma decimal / dot thousands). Returns None if the text is not a
    well-formed price.
    """
    if not text:
        return None
    digits = re.sub(r"[^\d.,]", "", text)
    if not digits:
        return None
    if "," in digits:
        # EU: '29,99' or '1.234,56'
        if re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d{1,2})?", digits):
            return float(digits.replace(".", "").replace(",", "."))
        # US: '1,299.99'
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", digits):
            return float(digits.replace(",", ""))
        return None
    # No comma: US plain '29.99' / '1000' or EU whole thousands '1.234'
    if re.fullmatch(r"\d+(?:\.\d{1,2})?", digits):
        return float(digits)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", digits):
        return float(digits.replace(".", ""))
    return None


def _apply_discount(price_info: dict) -> None:
    """If both current and original prices are present, compute savings/discount."""
    current = _to_amount(price_info.get('current_price'))
    original = _to_amount(price_info.get('original_price'))
    # No, or equal, prices means nothing to discount.
    if not current or not original or original <= current:
        return

    savings = original - current
    currency_match = re.search(_CURRENCY_SYMBOL, price_info.get('current_price') or '')
    currency_sym = currency_match.group(0) if currency_match else '$'
    price_info['savings_amount'] = f"{currency_sym}{savings:.2f}"
    price_info['discount_percentage'] = f"{int((savings / original) * 100)}%"
    price_info['is_on_sale'] = True


def _extract_original_price(soup: BeautifulSoup) -> str | None:
    """Extract original/list price if item is on sale."""
    for selector in ORIGINAL_PRICE_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text and re.search(_CURRENCY_SYMBOL, text):
                return text

    # Look for "Was" or "List Price" text patterns
    for elem in soup.select('.a-text-price'):
        text = elem.get_text(strip=True)
        if 'was' in text.lower() or 'list price' in text.lower():
            price_match = re.search(_AMOUNT_RE, text)
            if price_match:
                return price_match.group(0)

    return None


def _extract_deal_info(soup: BeautifulSoup) -> dict:
    """Extract deal/badge information."""
    deal_info = {
        'deal_type': None,
        'is_on_sale': False
    }

    deal_text = ""
    for selector in DEAL_SELECTORS:
        el = soup.select_one(selector)
        if el:
            deal_text = el.get_text(strip=True)
            if deal_text:
                break

    # Also check for Lightning Deal, Deal of the Day, etc. in other places
    if not deal_text:
        deal_elements = soup.select('[data-hook="deal-badge"], .a-badge-span')
        for el in deal_elements:
            text = el.get_text(strip=True)
            if text and any(deal_word in text.lower() for deal_word in
                           ['deal', 'lightning', 'discount', 'save', 'off', 'sale']):
                deal_text = text
                break

    if deal_text:
        deal_info['deal_type'] = deal_text
        deal_info['is_on_sale'] = True

    for selector in COUPON_SELECTORS:
        if soup.select_one(selector):
            deal_info['is_on_sale'] = True
            if not deal_info['deal_type']:
                deal_info['deal_type'] = 'Coupon'
            break

    return deal_info
