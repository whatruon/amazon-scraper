from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import Product

log = logging.getLogger(__name__)

PRICE_SELECTORS = [
    "#corePrice_feature_div .a-offscreen",
    "#corePrice_desktop .a-offscreen",
    "#unifiedPrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .aok-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#apex-pricetopay-accessibility-label",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
]


def _extract_price_from_soup(soup: BeautifulSoup) -> Optional[str]:
    for sel in PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text

    for price_tag in soup.select(".a-price:not(.a-text-price)"):
        off = price_tag.select_one(".a-offscreen")
        if off:
            text = off.get_text(strip=True)
            if text and not price_tag.find_parent(lambda t: t.name == "div" and t.get("id", "").startswith("CardInstance")):
                return text

    return None


def _extract_price_from_browser(page) -> Optional[str]:
    js = """
    () => {
        const containers = [
            '#corePrice_feature_div',
            '#corePrice_desktop',
            '#unifiedPrice_feature_div',
            '#corePriceDisplay_desktop_feature_div',
            '#price_inside_buybox',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
        ];
        for (const sel of containers) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const txt = el.innerText.trim();
            const m = txt.match(/\\$\\d+(?:,\\d{3})*(?:\\.\\d{2})?/);
            if (m) return m[0];
        }
        return null;
    }
    """
    return page.evaluate(js)


def extract_price(soup: BeautifulSoup, page=None) -> Optional[str]:
    price = _extract_price_from_soup(soup)
    if price:
        return price
    if page:
        return _extract_price_from_browser(page)
    return None


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    el = soup.select_one("#productTitle")
    if el:
        return el.get_text(strip=True)
    el = soup.select_one("title")
    if el:
        text = el.get_text(strip=True)
        text = re.sub(r"\s*:\s*Amazon\..*", "", text, flags=re.IGNORECASE)
        return text.strip()
    return None


def _extract_rating(soup: BeautifulSoup) -> Optional[str]:
    el = soup.select_one("span[data-hook='rating-out-of-text']")
    if el:
        return el.get_text(strip=True)
    el = soup.select_one(".a-icon-alt")
    if el:
        text = el.get_text(strip=True)
        m = re.search(r"[\d.]+ out of 5", text)
        if m:
            return m.group()
    return None


def _extract_review_count(soup: BeautifulSoup) -> Optional[str]:
    el = soup.select_one("span[data-hook='total-review-count']")
    if el:
        return el.get_text(strip=True)
    el = soup.select_one("#acrCustomerReviewText")
    if el:
        return el.get_text(strip=True)
    return None


MIN_IMAGE_SIZE = 200


def _is_large_image(url: str) -> bool:
    m = re.search(r"_(?:SX|SY|SL|SS|US|SR)(\d+)_", url)
    if m:
        return int(m.group(1)) >= MIN_IMAGE_SIZE
    return True  # no size pattern in URL, keep it


def _extract_images(soup: BeautifulSoup) -> list[str]:
    seen: set[str] = set()
    images: list[str] = []

    # Search across both main image area and thumbnail strip
    for img in soup.select("#imgTagWrapperId img, #main-image-container img, #altImages img, .imgTagWrapper img, #landingImage, #main-image"):
        for attr in ("data-old-hires", "src"):
            val = img.get(attr)
            if val and val not in seen and _is_large_image(val):
                # Parse out the base image path to normalize size variants
                base = re.sub(r"\._(AC|SX|SY|SL|SS|US|SR|FM|UX|V1|BG|PK)[^.]*_\.", ".", val)
                if base not in seen:
                    seen.add(base)
                    seen.add(val)
                    images.append(val)

    # Also try data-a-dynamic-image on the wrappers
    for container in soup.select("#imgTagWrapperId, #main-image-container, #altImages"):
        dyn = container.get("data-a-dynamic-image")
        if dyn:
            try:
                import json
                parsed = json.loads(dyn)
                candidates = sorted(parsed.keys(), key=lambda u: parsed[u][0], reverse=True)
                for url in candidates:
                    if max(parsed[url]) > 500 and url not in seen:
                        seen.add(url)
                        images.append(url)
            except (json.JSONDecodeError, TypeError):
                pass

    return images


def _extract_bullets(soup: BeautifulSoup) -> list[str]:
    seen: set[str] = set()
    bullets: list[str] = []
    for li in soup.select("#feature-bullets li"):
        text = " ".join(li.stripped_strings)
        text = text.strip()
        if not text or len(text) < 5:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        bullets.append(text)
    return bullets


def _extract_availability(soup: BeautifulSoup) -> Optional[str]:
    el = soup.select_one("#availability span")
    if el:
        text = el.get_text(strip=True)
        if text:
            return text
    el = soup.select_one("#deliveryBlockMessage")
    if el:
        text = el.get_text(strip=True)
        if text:
            return text
    return None


def _extract_asin(soup: BeautifulSoup, url: str) -> Optional[str]:
    m = re.search(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})", url)
    if m:
        return m.group(1)
    for meta in soup.select("meta[name='asin']"):
        asin = meta.get("content")
        if asin and re.match(r"^[A-Z0-9]{10}$", asin):
            return asin
    input_el = soup.select_one("input[name='ASIN']")
    if input_el:
        asin = input_el.get("value")
        if asin and re.match(r"^[A-Z0-9]{10}$", asin):
            return asin
    return None


def _extract_brand(soup: BeautifulSoup) -> Optional[str]:
    # Try product details table
    for row in soup.select("#productDetails_detailBullets_sections1 tr, #prodDetails tr, #productDetails_techSpec_section_1 tr"):
        th = row.select_one("th, .a-span3")
        if th and re.search(r"\bbrand\b", th.get_text(strip=True), re.IGNORECASE):
            td = row.select_one("td, .a-span9")
            if td:
                return td.get_text(strip=True)
    # Try brand link
    el = soup.select_one("#bylineInfo")
    if el:
        return el.get_text(strip=True)
    el = soup.select_one("a.brand-link, a[href*='/stores/brand/'], #po-brand .a-span2")
    if el:
        return el.get_text(strip=True)
    # Try brand from product overview
    for row in soup.select("#productOverview_feature_div tr, .po-brand"):
        th = row.select_one("td:first-child, .a-span3")
        if th and re.search(r"\bbrand\b", th.get_text(strip=True), re.IGNORECASE):
            td = row.select_one("td:nth-child(2), .a-span9")
            if td:
                return td.get_text(strip=True)
    return None


def parse_search_results(html: str) -> list[str]:
    """Parse Amazon search results page and return a list of product URLs."""
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []

    for card in soup.select('[data-component-type="s-search-result"]'):
        link = card.select_one("h2 a.a-link-normal, h2 a.a-text-normal")
        if not link:
            link = card.select_one("a.a-link-normal.s-link-style")
        if link:
            href = link.get("href", "")
            if href and "/dp/" in href:
                # Strip tracking query parameters
                clean = re.sub(r"\?.*$", "", href)
                if clean.startswith("/"):
                    clean = "https://www.amazon.com" + clean
                elif not clean.startswith("http"):
                    clean = "https://www.amazon.com/" + clean.lstrip("/")
                if clean not in urls:
                    urls.append(clean)

    # Also extract from pagination links if present
    for a in soup.select("a.s-pagination-item"):
        href = a.get("href", "")
        if href and "/s?" in href:
            if not href.startswith("http"):
                href = "https://www.amazon.com" + href
            # We don't add pagination URLs to the result list;
            # the caller can use these to fetch more result pages.

    return urls


def parse_product(html: str, url: str = "") -> Product:
    soup = BeautifulSoup(html, "lxml")
    return Product(
        title=_extract_title(soup),
        price=_extract_price_from_soup(soup),
        rating=_extract_rating(soup),
        review_count=_extract_review_count(soup),
        images=_extract_images(soup),
        bullets=_extract_bullets(soup),
        availability=_extract_availability(soup),
        asin=_extract_asin(soup, url),
        brand=_extract_brand(soup),
    )


def enrich_from_browser(product: Product, page) -> Product:
    if not product.price:
        browser_price = _extract_price_from_browser(page)
        if browser_price:
            product.price = browser_price
            log.info("price filled from browser: %s", browser_price)
        else:
            log.info("no price found from browser or HTML")
    return product
