from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from .models import Product

log = logging.getLogger(__name__)


def track_price(page: Page) -> dict:
    """
    Extract price and deal information from Amazon product page.

    Args:
        page: Playwright Page object

    Returns:
        Dictionary containing price information:
        - current_price: Current price as string (e.g., "$29.99")
        - original_price: Original price if on sale (e.g., "$39.99")
        - discount_percentage: Discount percentage if on sale
        - deal_type: Type of deal (e.g., "Lightning Deal", "Deal of the Day")
        - is_on_sale: Boolean indicating if product is on sale
        - savings_amount: Amount saved if on sale
    """
    price_info = {
        'current_price': None,
        'original_price': None,
        'discount_percentage': None,
        'deal_type': None,
        'is_on_sale': False,
        'savings_amount': None
    }

    try:
        # Get page content
        content = page.content()
        soup = BeautifulSoup(content, "lxml")

        # Extract current price using existing parser logic
        current_price = _extract_current_price(soup, page)
        if current_price:
            price_info['current_price'] = current_price

        # Check for original price (list price/was price)
        original_price = _extract_original_price(soup)
        if original_price:
            price_info['original_price'] = original_price

        # Check for deal/badges
        deal_info = _extract_deal_info(soup)
        price_info.update(deal_info)

        # Calculate discount if we have both prices
        if price_info['current_price'] and price_info['original_price']:
            try:
                current_val = float(re.sub(r'[^\d.]', '', price_info['current_price']))
                original_val = float(re.sub(r'[^\d.]', '', price_info['original_price']))
                if original_val > current_val:
                    savings = original_val - current_val
                    price_info['savings_amount'] = f"${savings:.2f}"
                    price_info['discount_percentage'] = f"{int((savings / original_val) * 100)}%"
                    price_info['is_on_sale'] = True
            except ValueError:
                pass

    except Exception as e:
        log.warning(f"Error tracking price: {e}")

    return price_info


def _extract_current_price(soup: BeautifulSoup, page) -> str | None:
    """Extract current price using existing parser logic."""
    from .parser import extract_price
    return extract_price(soup, page)


def _extract_original_price(soup: BeautifulSoup) -> str | None:
    """Extract original/list price if item is on sale."""
    # Common selectors for original/was price
    original_price_selectors = [
        '#priceblock_dealprice',  # Lightning Deal price (sometimes shows as original)
        '.a-text-price .a-offscreen',  # Strike-through price
        '#listPrice .a-offscreen',
        '#priceblock_ourprice .a-text-price .a-offscreen',
        '.a-size-base.a-color-secondary .a-offscreen',  # List price
        '[data-testid="odal-original-price"] .a-offscreen',
        '.a-section.a-spacing.microverse .a-text-price span',
    ]

    for selector in original_price_selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text and ('$' in text or '₹' in text or '£' in text or '€' in text):
                return text

    # Look for "Was" or "List Price" text patterns
    was_price_elements = soup.select('.a-text-price')
    for elem in was_price_elements:
        text = elem.get_text(strip=True)
        if 'was' in text.lower() or 'list price' in text.lower():
            price_match = re.search(r'[\$₹£€]\d+(?:,\d{3})*(?:\.\d{2})?', text)
            if price_match:
                return price_match.group(0)

    return None


def _extract_deal_info(soup: BeautifulSoup) -> dict:
    """Extract deal/badge information."""
    deal_info = {
        'deal_type': None,
        'is_on_sale': False
    }

    # Deal/badge selectors
    deal_selectors = [
        '#dealBadge_feature_div',
        '#dealBadge',
        '.dealBadge',
        '[data-hawkeye-key="mkcp.dealbadge"]',
        '.dealLabel',
        '.a-badge.aok-align-bottom',
        '.a-row.a-spacing-mini .a-color-price',
        '#saleBadge',
        '.a-row.a-size-base.a-color-price'
    ]

    deal_text = ""
    for selector in deal_selectors:
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

    # Check for coupon/discount indicators
    coupon_selectors = [
        '.couponBadge',
        '[data-hook="promo-price"]',
        '.a-section.couponClippableBlock',
        '.promoBadge'
    ]

    for selector in coupon_selectors:
        if soup.select_one(selector):
            deal_info['is_on_sale'] = True
            if not deal_info['deal_type']:
                deal_info['deal_type'] = 'Coupon'
            break

    return deal_info