from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from .models import Product

log = logging.getLogger(__name__)


def scrape_seller_info(page: Page) -> dict:
    """
    Extract seller information from Amazon product page.

    Args:
        page: Playwright Page object

    Returns:
        Dictionary containing seller information:
        - seller_name: Name of the seller
        - fulfilled_by_amazon: Whether product is fulfilled by Amazon
        - seller_rating: Seller rating (if available)
        - seller_rating_count: Number of seller ratings
        - buybox_owner: Whether seller owns the Buy Box
        - ships_from: Location ships from
    """
    seller_info = {
        'seller_name': None,
        'fulfilled_by_amazon': False,
        'seller_rating': None,
        'seller_rating_count': None,
        'buybox_owner': False,
        'ships_from': None
    }

    try:
        # Get page content
        content = page.content()
        soup = BeautifulSoup(content, "lxml")

        # Extract seller name
        seller_name = _extract_seller_name(soup)
        if seller_name:
            seller_info['seller_name'] = seller_name

        # Check if fulfilled by Amazon
        fulfilled_by_amazon = _is_fulfilled_by_amazon(soup)
        seller_info['fulfilled_by_amazon'] = fulfilled_by_amazon

        # Extract seller rating
        seller_rating, rating_count = _extract_seller_rating(soup)
        if seller_rating:
            seller_info['seller_rating'] = seller_rating
        if rating_count:
            seller_info['seller_rating_count'] = rating_count

        # Check if seller owns the Buy Box
        buybox_owner = _is_buybox_owner(soup)
        seller_info['buybox_owner'] = buybox_owner

        # Extract ships from location
        ships_from = _extract_ships_from(soup)
        if ships_from:
            seller_info['ships_from'] = ships_from

    except Exception as e:
        log.warning(f"Error scraping seller info: {e}")

    return seller_info


def _extract_seller_name(soup: BeautifulSoup) -> str | None:
    """Extract seller/merchant name."""
    # Common selectors for seller information
    seller_selectors = [
        '#bylineInfo',
        '#bylineInfo_feature_div',
        '#merchant-info',
        '#merchantInfo',
        '[data-feature-name="bylineInfo"]',
        '#byline',
        '#bylineInfo_text',
        '.tabular-buybox-text:nth-child(2) span'
    ]

    for selector in seller_selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            # Clean up common prefixes
            text = re.sub(r'^(?:Visit the|Visit the|Sold by:?\s*)', '', text, flags=re.IGNORECASE)
            text = text.strip()
            if text and text != "" and len(text) > 1:
                # Avoid generic text like "See more"
                if not text.lower().startswith(('see', 'visit', 'more')):
                    return text

    # Alternative: look for "Sold by:" text
    sold_by_elements = soup.find_all(string=re.compile(r'Sold by:', re.I))
    for element in sold_by_elements:
        parent = element.parent
        if parent:
            # Look for the seller name nearby
            seller_el = parent.find_next(['span', 'a'])
            if seller_el:
                seller_text = seller_el.get_text(strip=True)
                if seller_text and len(seller_text) > 1:
                    return seller_text

    return None


def _is_fulfilled_by_amazon(soup: BeautifulSoup) -> bool:
    """Check if product is fulfilled by Amazon."""
    fba_selectors = [
        '#tabular-buybox[data-csa-c-content-id="btfbb"]',
        '#tabular-buybox',
        '#shippingMethod',
        '#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE',
        '#deliveryBlockMessage',
        '#usp fulfullment-message'
    ]

    fba_keywords = [
        'fulfilled by amazon',
        'ships from amazon',
        'shipped from amazon',
        'free shipping',
        'prime',
        'amazon prime'
    ]

    # Check specific FBA elements
    for selector in fba_selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True).lower()
            if any(keyword in text for keyword in fba_keywords):
                return True

    # Check for Prime logo
    prime_logo = soup.select_one('#primeLogo, .a-icon-prime, [data-analytics="prime"]')
    if prime_logo:
        return True

    # Check for "Sold by Amazon" or "Ships from Amazon"
    amazon_text_elements = soup.find_all(string=re.compile(r'(sold by amazon|ships from amazon|fulfilled by amazon)', re.I))
    if amazon_text_elements:
        return True

    return False


def _extract_seller_rating(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract seller rating and rating count."""
    # Seller rating selectors
    rating_selectors = [
        '#sellerProfileTriggerId',
        '#merchant-vars:not(:empty)',
        '[data-hook="avg-star-rating"]',
        '#avgRating',
        '.reviewCountTextLinkedHistogram'
    ]

    rating_text = None
    rating_count = None

    for selector in rating_selectors:
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
                if rating_text or rating_count:
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


def _is_buybox_owner(soup: BeautifulSoup) -> bool:
    """Check if the seller owns the Buy Box."""
    # The seller in the Buy Box is typically the first/seller featured in:
    buybox_selectors = [
        '#buybox-see-all-buying-choices',
        '#buybox',
        '#BuyBox',
        '#mbc',
        '#merchant-info',
        '#merchantDetails'
    ]

    # Look for "Sold by" near the price/add to cart area
    price_area = soup.select_one('#corePrice_feature_div, #corePriceDisplay_desktop_feature_div, #buybox')
    if price_area:
        sold_by_text = price_area.find(string=re.compile(r'Sold by:', re.I))
        if sold_by_text:
            # If we found "Sold by:" in the price area, it's likely the Buy Box seller
            return True

    # Check if the seller name appears near the Add to Cart button
    add_to_cart_buttons = soup.select('#add-to-cart-button, #buy-now-button')
    for button in add_to_cart_buttons:
        # Look for seller info near the button
        parent = button.find_parent()
        if parent:
            seller_text = parent.get_text()
            if 'sold by' in seller_text.lower() or 'fulfilled by' in seller_text.lower():
                return True

    # Default assumption: if we found a seller name and it's prominent, assume Buy Box owner
    seller_name = _extract_seller_name(soup)
    if seller_name:
        # Check if it's in prominent locations
        prominent_selectors = ['#btfbb', '#merchant-info', '#merchantInfo', '#mir-layout-DELIVERY_BLOCK']
        for selector in prominent_selectors:
            el = soup.select_one(selector)
            if el and seller_name.lower() in el.get_text().lower():
                return True

    return False


def _extract_ships_from(soup: BeautifulSoup) -> str | None:
    """Extract where the item ships from."""
    ships_from_selectors = [
        '#shipsFrom',
        '#shipsFromDetail',
        '.tabular-buybox-text',
        '#deliveryBlockMessage',
        '#ubb-ufss-slot',
        '#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE'
    ]

    for selector in ships_from_selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) > 3:
                # Clean up common prefixes
                text = re.sub(r'^(?:ships from|ships from:?\s*)', '', text, flags=re.IGNORECASE)
                text = text.strip()
                if text:
                    return text

    # Look for "Ships from" text pattern
    ships_from_elements = soup.find_all(string=re.compile(r'Ships from:', re.I))
    for element in ships_from_elements:
        parent = element.parent
        if parent:
            # Get the next sibling or parent text
            ships_text = parent.get_text(strip=True)
            ships_text = re.sub(r'^.*?Ships from:\s*', '', ships_text, flags=re.IGNORECASE)
            ships_text = ships_text.strip()
            if ships_text and len(ships_text) > 2:
                return ships_text

    return None