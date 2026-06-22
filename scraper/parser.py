from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import Product

log = logging.getLogger(__name__)

# Price-to-pay first. Ordered most→least trustworthy. Generic `.a-offscreen` is
# deliberately NOT here: it grabs the first price on the page, which is usually a
# struck-through list price or a per-unit/related-item price, not what you pay.
PRICE_SELECTORS = [
    "#apex-pricetopay-accessibility-label",
    "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
    "#corePrice_feature_div .priceToPay .a-offscreen",
    "#corePrice_feature_div .a-price:not([data-a-color='secondary']) .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    ".priceToPay .a-offscreen",
]

# A currency token: glyph ($ € £ ¥ ₹ etc.) or a 3-letter code (USD, GBP, AED, ...),
# on either side of a locale-formatted number ($1,299.00 / 188,96 € / AED 827.95).
_CUR = r"[$€£¥₹₪₩]|[A-Z]{3}|د\\.إ|ر\\.س"
_SP = "  "  # nbsp / narrow nbsp, used abroad as thousands separators
_PRICE_RE = re.compile(
    rf"(?P<pre>{_CUR})?\s*"
    rf"(?P<num>\d[\d.,{_SP} ]*\d|\d)"
    rf"\s*(?P<post>{_CUR})?"
)

def normalize_price(text: Optional[str]) -> Optional[str]:
    """Pull a clean, currency-preserving price out of arbitrary text, or None.

    Keeps the marketplace's own symbol/code and number format (so amazon.de gives
    "188,96 €" and amazon.ae "AED 827.95", not a US-ified "$188.96"). A label like
    "$275.00 with 5% off" yields just "$275.00"; junk with no number -> None.
    """
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    num = m.group("num").replace(" ", " ").replace(" ", " ").strip()
    if not any(c.isdigit() for c in num):
        return None
    if m.group("pre"):
        sym = m.group("pre")
        sep = " " if sym.isalpha() else ""  # "AED 827.95" but "$278.00"
        return f"{sym}{sep}{num}"
    if m.group("post"):
        return f"{num} {m.group('post')}"
    return num


def _price_from_parts(soup: BeautifulSoup) -> Optional[str]:
    core = soup.select_one("#corePrice_feature_div, #corePriceDisplay_desktop_feature_div") or soup
    whole = core.select_one(".priceToPay .a-price-whole") or core.select_one(".a-price-whole")
    if not whole:
        return None
    parent = whole.find_parent(class_="a-price")
    scope = parent if parent else core
    fraction = scope.select_one(".a-price-fraction")
    symbol = scope.select_one(".a-price-symbol")
    decimal = scope.select_one(".a-price-decimal")

    dec = (decimal.get_text(strip=True) if decimal else ".") or "."
    # whole includes the nested decimal char (e.g. "1.299," on amazon.de); drop it.
    whole_text = whole.get_text(strip=True)
    if whole_text.endswith(dec):
        whole_text = whole_text[: -len(dec)]
    whole_text = whole_text.rstrip(".,   ")
    frac = fraction.get_text(strip=True) if fraction else "00"
    sym = symbol.get_text(strip=True) if symbol else ""
    return normalize_price(f"{sym}{whole_text}{dec}{frac}")


def _extract_price_from_soup(soup: BeautifulSoup) -> Optional[str]:
    for sel in PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            price = normalize_price(el.get_text(strip=True))
            if price:
                return price
    return _price_from_parts(soup)


def _extract_price_from_browser(page) -> Optional[str]:
    js = r"""
    () => {
        // currency-preserving: keep the marketplace symbol/code and its number format
        const CUR = "[$€£¥₹₪₩]|[A-Z]{3}|د\\.إ|ر\\.س";
        const RE = new RegExp("(" + CUR + ")?\\s*(\\d[\\d.,   ]*\\d|\\d)\\s*(" + CUR + ")?");
        const norm = (t) => {
            if (!t) return null;
            const m = RE.exec(t);
            if (!m) return null;
            const num = m[2].replace(/[  ]/g, ' ').trim();
            if (!/\d/.test(num)) return null;
            if (m[1]) return m[1] + (/^[A-Z]{3}$/.test(m[1]) ? ' ' : '') + num;
            if (m[3]) return num + ' ' + m[3];
            return num;
        };
        // price-to-pay only; never a generic .a-offscreen (catches list/unit prices)
        const selectors = [
            '#apex-pricetopay-accessibility-label',
            '#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen',
            '#corePrice_feature_div .priceToPay .a-offscreen',
            "#corePrice_feature_div .a-price:not([data-a-color='secondary']) .a-offscreen",
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '#price_inside_buybox',
            '.priceToPay .a-offscreen',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            const p = el && norm(el.innerText);
            if (p) return p;
        }
        const core = document.querySelector('#corePrice_feature_div, #corePriceDisplay_desktop_feature_div') || document;
        const whole = core.querySelector('.priceToPay .a-price-whole') || core.querySelector('.a-price-whole');
        if (whole) {
            const scope = whole.closest('.a-price') || core;
            const sym = scope.querySelector('.a-price-symbol');
            const dec = scope.querySelector('.a-price-decimal');
            const frac = scope.querySelector('.a-price-fraction');
            const d = (dec ? dec.innerText.trim() : '.') || '.';
            let w = whole.innerText.trim();
            if (w.endsWith(d)) w = w.slice(0, -d.length);
            return norm((sym ? sym.innerText.trim() : '') + w + d + (frac ? frac.innerText.trim() : '00'));
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


# Amazon bakes the rendered size into the filename as dot-separated tokens after
# the image ID (which never contains a dot), e.g.
#   .../I/61O3iMlnJIL._AC_SL1500_.jpg          (1500px)
#   .../I/31fEv99XZ+L._AC_US40_.jpg            (40px thumbnail)
#   .../I/61ChRZ7BPwL.SS40_BG85,85,85_...__.jpg (video play-icon overlay)
# Dropping every token between the ID and the extension returns the original.
_IMG_ID = re.compile(r"(/images/I/[^/.]+)\.[^/]*(\.[a-zA-Z]+)$")
# Fallback for other hosts: strip a single ._..._ size token.
_IMG_SIZE_TOKEN = re.compile(r"\._[^/]*?(?=\.[a-zA-Z]+$)")


def full_size_image(url: str) -> str:
    m = _IMG_ID.match(url) or _IMG_ID.search(url)
    if m:
        return url[: m.start(1)] + m.group(1) + m.group(2)
    return _IMG_SIZE_TOKEN.sub("", url)


def _extract_images(soup: BeautifulSoup) -> list[str]:
    seen: set[str] = set()
    images: list[str] = []

    def add(url: Optional[str]) -> None:
        if not url:
            return
        full = full_size_image(url)
        if full not in seen:
            seen.add(full)
            images.append(full)

    for img in soup.select("#altImages img, #imgTagWrapperId img"):
        add(img.get("data-old-hires"))
        add(img.get("src"))

        dyn = img.get("data-a-dynamic-image")
        if dyn:
            try:
                import json
                parsed = json.loads(dyn)
                # highest-resolution variant first
                urls = sorted(parsed.keys(), key=lambda u: parsed[u][0], reverse=True)
                if urls:
                    add(urls[0])
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
