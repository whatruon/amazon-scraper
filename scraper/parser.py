from __future__ import annotations

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import Product, SearchResult
from .config import (
    PRICE_SELECTORS,
    BRAND_SELECTORS,
    PRODUCT_DETAILS_SELECTORS,
    CATEGORY_SELECTORS,
    VARIANT_SELECTORS,
    MIN_IMAGE_SIZE,
)

log = logging.getLogger(__name__)


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
    """Extract price via browser JS evaluation. Uses the same selectors as _extract_price_from_soup."""
    selectors_json = json.dumps(PRICE_SELECTORS)
    js = f"""
    () => {{
        const containers = {selectors_json};
        for (const sel of containers) {{
            const el = document.querySelector(sel);
            if (!el) continue;
            const txt = el.innerText.trim();
            const m = txt.match(/[$£€¥₹]\\d+(?:,\\d{3})*(?:\\.\\d{{2}})?/);
            if (m) return m[0];
        }}
        return null;
    }}
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
                base = re.sub(r"\._(AC|SX|SY|SL|SS|US|SR|FM|UX|V1|BG|PK)[^.]*?_\.", ".", val)
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
    m = re.search(r"/(?:dp|gp/product|product)/([A-Za-z0-9]{10})", url)
    if m:
        return m.group(1).upper()
    for meta in soup.select("meta[name='asin']"):
        asin = meta.get("content")
        if asin and re.match(r"^[A-Za-z0-9]{10}$", asin):
            return asin
    input_el = soup.select_one("input[name='ASIN']")
    if input_el:
        asin = input_el.get("value")
        if asin and re.match(r"^[A-Za-z0-9]{10}$", asin):
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
        text = el.get_text(strip=True)
        # Clean up common patterns: "Visit the Sony Store" -> "Sony", "Brand: Sony" -> "Sony"
        text = re.sub(r'^(?:Visit\s+the\s+|Brand:\s*)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+(?:Store|Brand|Shop)$', '', text, flags=re.IGNORECASE)
        return text.strip()
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


def parse_search_card(html: str, domain: str = "www.amazon.com") -> list[SearchResult]:
    """Parse Amazon search results page and return structured SearchResult objects."""
    soup = BeautifulSoup(html, "lxml")
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for card in soup.select('[data-component-type="s-search-result"]'):
        link = card.select_one("h2 a.a-link-normal, h2 a.a-text-normal")
        if not link:
            link = card.select_one("a.a-link-normal.s-link-style")
        if not link:
            continue

        href = link.get("href", "")
        if not href or not ("/dp/" in href or "/gp/product/" in href or "/product/" in href):
            continue

        # Strip tracking query parameters
        clean = re.sub(r"\?.*$", "", href)
        if clean.startswith("/"):
            clean = f"https://{domain}" + clean
        elif not clean.startswith("http"):
            clean = f"https://{domain}/" + clean.lstrip("/")

        if clean in seen_urls:
            continue
        seen_urls.add(clean)

        # Extract ASIN from URL
        m = re.search(r"/(?:dp|gp/product|product)/([A-Za-z0-9]{10})", clean)
        asin = m.group(1).upper() if m else None

        # Extract title
        title = link.get("title")
        if not title:
            title = link.get_text(strip=True)

        # Extract price
        price = None
        whole_el = card.select_one(".a-price .a-price-whole")
        if whole_el:
            price_text = whole_el.get_text(strip=True)
            fraction_el = card.select_one(".a-price .a-price-fraction")
            if fraction_el:
                frac = fraction_el.get_text(strip=True)
                if frac:
                    price_text += "." + frac
            symbol_el = card.select_one(".a-price-symbol")
            symbol = symbol_el.get_text(strip=True) if symbol_el else "$"
            price = symbol + price_text

        # Extract rating
        rating = None
        rating_el = card.select_one("i.a-icon-star, i.a-icon-star-small, span.a-icon-alt")
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            rm = re.search(r"[\d.]+ out of 5", rating_text)
            if rm:
                rating = rm.group()

        # Extract review count
        review_count = None
        review_el = card.select_one("span.a-size-base.s-underline-text")
        if not review_el:
            review_el = card.select_one("a.a-size-base[href*='customer-reviews']")
        if not review_el:
            review_el = card.select_one("span.a-size-base[aria-label*='ratings']")
        if review_el:
            text = review_el.get_text(strip=True).replace(",", "")
            if text.isdigit():
                review_count = text

        # Check for Prime
        is_prime = bool(card.select_one("i.a-icon-prime, i.a-icon-prime-small"))

        results.append(
            SearchResult(
                url=clean,
                asin=asin,
                title=title,
                price=price,
                rating=rating,
                review_count=review_count,
                is_prime=is_prime,
            )
        )

    return results


def parse_search_results(html: str, domain: str = "www.amazon.com") -> list[str]:
    """Compat wrapper — returns only URLs. Prefer parse_search_card for structured data."""
    return [r.url for r in parse_search_card(html, domain)]


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
    """Fill missing product.price via browser JS evaluation. MUTATES the product in-place."""
    if not product.price:
        browser_price = _extract_price_from_browser(page)
        if browser_price:
            product.price = browser_price
            log.info("price filled from browser: %s", browser_price)
        else:
            log.info("no price found from browser or HTML")
    return product
