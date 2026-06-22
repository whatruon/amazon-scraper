from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import Product

log = logging.getLogger(__name__)

PRICE_SELECTORS = [
    "#apex-pricetopay-accessibility-label",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    ".a-price .a-offscreen",
    ".a-offscreen",
]

COUPON_PATTERNS = re.compile(
    r"coupon|savings|subscribe|save\s+\$|-\$|with\s+coupon|clip\s+coupon",
    re.IGNORECASE,
)


def _extract_price_from_soup(soup: BeautifulSoup) -> Optional[str]:
    for sel in PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text

    whole = soup.select_one(".a-price-whole")
    if whole:
        whole_text = whole.get_text(strip=True).rstrip(".")
        fraction = soup.select_one(".a-price-fraction")
        symbol = soup.select_one(".a-price-symbol")
        frac = fraction.get_text(strip=True) if fraction else "00"
        sym = symbol.get_text(strip=True) if symbol else "$"
        return f"{sym}{whole_text}.{frac}"

    return None


def _extract_price_from_browser(page) -> Optional[str]:
    js = """
    () => {
        const selectors = [
            '#apex-pricetopay-accessibility-label',
            '#corePrice_feature_div .a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '#price_inside_buybox',
            '.a-price .a-offscreen',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && el.innerText.trim()) return el.innerText.trim();
        }
        const whole = document.querySelector('.a-price-whole');
        if (whole) {
            const sym = document.querySelector('.a-price-symbol');
            const frac = document.querySelector('.a-price-fraction');
            return (sym ? sym.innerText.trim() : '$') + whole.innerText.trim().replace(/\\.$/, '') + '.' + (frac ? frac.innerText.trim() : '00');
        }
        const dp = document.getElementById('dp') || document.getElementById('ppd') || document.querySelector('#centerCol, #leftCol');
        if (dp) {
            const matches = dp.innerText.match(/\\$\\d+(?:,\\d{3})*(?:\\.\\d{2})?/g);
            if (matches) {
                const nums = matches.map(m => parseFloat(m.replace(/[$,]/g, ''))).filter(n => n > 5);
                if (nums.length) return '$' + Math.max(...nums).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
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


def _extract_images(soup: BeautifulSoup) -> list[str]:
    seen: set[str] = set()
    images: list[str] = []

    for img in soup.select("#altImages img, #imgTagWrapperId img"):
        for attr in ("data-old-hires", "src"):
            val = img.get(attr)
            if val and val not in seen:
                seen.add(val)
                images.append(val)

        dyn = img.get("data-a-dynamic-image")
        if dyn:
            try:
                import json
                parsed = json.loads(dyn)
                urls = sorted(parsed.keys(), key=lambda u: parsed[u][0], reverse=True)
                if urls and urls[0] not in seen:
                    seen.add(urls[0])
                    images.append(urls[0])
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
        return el.get_text(strip=True)
    el = soup.select_one("#deliveryBlockMessage")
    if el:
        return el.get_text(strip=True)
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
    )


def enrich_from_browser(product: Product, page) -> Product:
    if not product.price:
        price = _extract_price_from_browser(page)
        if price:
            product.price = price
            log.info("price filled from browser fallback: %s", price)
    return product
