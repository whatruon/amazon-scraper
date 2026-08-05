from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from .config import (
    AVAILABILITY_SELECTORS,
    BRAND_SELECTORS,
    IMAGE_CONTAINER_SELECTORS,
    IMAGE_SELECTORS,
    MIN_IMAGE_SIZE,
    PRICE_SELECTORS,
    PRODUCT_DETAILS_SELECTORS,
    RATING_SELECTORS,
    REVIEW_COUNT_SELECTORS,
    SEARCH_RESULT_SELECTORS,
    SEARCH_TITLE_SELECTORS,
    TITLE_SELECTORS,
)
from .models import Product, SearchResult

log = logging.getLogger(__name__)

# Character class of the currency symbols Amazon uses. Escaped to be safe inside
# a JS regex literal (the class may not be representable without escaping).
_CURRENCY_CLASS = r"[$£€¥₹]"

# Common localized "X out of 5" rating phrases, so EU pages (amazon.de renders
# "4,7 von 5 Sternen", amazon.fr "4,7 sur 5 étoiles", etc.) are normalized.
_RATING_PHRASE = r"(\d+[\.,]?\d*)\s*(?:von|sur|de|su|av|aus|van|da|af|di|over|of|out\s*of)\s*5\b"


def _normalize_rating(text: str) -> str | None:
    """Normalize a localized rating text to 'X out of 5' with a dot decimal.

    Accepts English ('4.7 out of 5'), German ('4,7 von 5 Sternen'), French
    ('4,7 sur 5 étoiles'), bare numbers ('4.7'), and comma decimals ('4,7').
    Returns None when no rating can be identified.
    """
    if not text:
        return None
    text = text.strip()
    m = re.search(_RATING_PHRASE, text, re.IGNORECASE)
    if m:
        value = m.group(1).replace(",", ".")
        try:
            rating = float(value)
        except ValueError:
            return None
        if not 0.0 <= rating <= 5.0:
            return None
        # Normalize over-precise decimals (e.g. '4,70' -> '4.7') so the output
        # still passes Product.validate_rating(), which accepts at most one
        # decimal place.
        if "." in value and len(value.rsplit(".", 1)[1]) > 1:
            value = f"{rating:.1f}"
        return f"{value} out of 5"
    if re.fullmatch(r"\d+\.?\d*", text):
        return text
    return None


def _extract_price_from_soup(soup: BeautifulSoup) -> str | None:
    """Extract a price from HTML using the standardized PRICE_SELECTORS list.

    Falls back to the generic Amazon price component, skipping elements embedded
    inside sponsored "CardInstance" containers.
    """
    for sel in PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            # Require an actual currency symbol so selectors matching labels/empty
            # wrappers are skipped.
            if text and re.search(_CURRENCY_CLASS, text):
                return text

    for price_tag in soup.select(".a-price:not(.a-text-price)"):
        # Ignore prices rendered inside sponsored/related cards.
        if price_tag.find_parent(lambda t: t.name == "div" and t.get("id", "").startswith("CardInstance")) is not None:
            continue
        off = price_tag.select_one(".a-offscreen")
        if off:
            text = off.get_text(strip=True)
            if text:
                return text

    return None


def _extract_price_from_browser(page) -> str | None:
    """Extract price via browser JS evaluation using the same selector list."""
    selectors_json = json.dumps(PRICE_SELECTORS)
    # Two forms: prefix symbol (US 'US$ 1,299.99') and trailing symbol (EU '1.234,56 €').
    prefix_re = rf"{_CURRENCY_CLASS}\s*\d+(?:,\d{{3}})*(?:\.\d{{1,2}})?"
    suffix_re = rf"\d+(?:\.\d{{3}})*(?:,\d{{1,2}})?\s*{_CURRENCY_CLASS}"
    js = f"""
    () => {{
        const containers = {selectors_json};
        const re = /(?:{prefix_re}|{suffix_re})/;
        for (const sel of containers) {{
            const el = document.querySelector(sel);
            if (!el) continue;
            const txt = el.innerText.trim();
            const m = txt.match(re);
            if (m) return m[0];
        }}
        return null;
    }}
    """
    try:
        return page.evaluate(js)
    except Exception as e:
        log.warning("Browser price extraction failed: %s", e)
        return None


# Re-usable entry point: prefers static HTML, falls back to browser JS evaluation.
def extract_price(soup: BeautifulSoup, page=None) -> str | None:
    """Extract a price. Uses *page* (browser) only when HTML yields none."""
    price = _extract_price_from_soup(soup)
    if price:
        return price
    if page is not None:
        return _extract_price_from_browser(page)
    return None


def _extract_title(soup: BeautifulSoup) -> str | None:
    for sel in TITLE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if sel == "title":
                text = re.sub(r"\s*:\s*Amazon\..*", "", text, flags=re.IGNORECASE)
            if text:
                return text.strip()
    return None


def _extract_rating(soup: BeautifulSoup) -> str | None:
    for sel in RATING_SELECTORS:
        el = soup.select_one(sel)
        if el:
            normalized = _normalize_rating(el.get_text(strip=True))
            if normalized:
                return normalized
    return None


def _extract_review_count(soup: BeautifulSoup) -> str | None:
    for sel in REVIEW_COUNT_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if not text:
                continue
            # "19,665 global ratings" -> "19665"; "1 global rating" -> "1".
            digits = re.sub(r"[^\d]", "", text)
            if digits:
                return digits
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
    for img in soup.select(", ".join(IMAGE_SELECTORS)):
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
    for container in soup.select(", ".join(IMAGE_CONTAINER_SELECTORS)):
        dyn = container.get("data-a-dynamic-image")
        if dyn:
            try:
                parsed = json.loads(dyn)
                candidates = sorted(parsed.keys(), key=lambda u: parsed[u][0], reverse=True)
                for url in candidates:
                    if max(parsed[url]) > 500:
                        # Same base image under a different size marker is a
                        # duplicate of one already captured by the <img> loop.
                        base = re.sub(r"\._(AC|SX|SY|SL|SS|US|SR|FM|UX|V1|BG|PK)[^.]*?_\.", ".", url)
                        if base in seen or url in seen:
                            continue
                        seen.add(base)
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


def _extract_availability(soup: BeautifulSoup) -> str | None:
    for sel in AVAILABILITY_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return None


def _extract_asin(soup: BeautifulSoup, url: str) -> str | None:
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


def _extract_brand(soup: BeautifulSoup) -> str | None:
    # Try product details table
    for row in soup.select(", ".join(PRODUCT_DETAILS_SELECTORS)):
        th = row.select_one("th, .a-span3")
        if th and re.search(r"\bbrand\b", th.get_text(strip=True), re.IGNORECASE):
            td = row.select_one("td, .a-span9")
            if td:
                return td.get_text(strip=True)
    # Try brand link / byline
    for sel in BRAND_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        if sel.startswith(("#po-brand", "#bylineInfo")):
            text = el.get_text(strip=True)
            if sel == "#bylineInfo":
                # Clean up common patterns: "Visit the Sony Store" -> "Sony", "Brand: Sony" -> "Sony"
                text = re.sub(r'^(?:Visit\s+the\s+|Brand:\s*)', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\s+(?:Store|Brand|Shop)$', '', text, flags=re.IGNORECASE)
            if text:
                return text.strip()
        else:
            text = el.get_text(strip=True)
            if text:
                return text.strip()
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

    for card in soup.select(", ".join(SEARCH_RESULT_SELECTORS)):
        link = None
        for sel in SEARCH_TITLE_SELECTORS:
            link = card.select_one(sel)
            if link:
                break
        if not link:
            continue

        href = link.get("href", "")
        if not href or not ("/dp/" in href or "/gp/product/" in href or "/product/" in href):
            continue

        # Strip tracking query parameters
        clean = re.sub(r"\?.*$", "", href)
        # Also drop the /ref=... path segment; path refs are just as
        # CAPTCHA-prone as query refs.
        clean = re.sub(r"/ref=[^/]*/?$", "", clean)
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
            whole = whole_el.get_text(strip=True)
            fraction_el = card.select_one(".a-price .a-price-fraction")
            frac = fraction_el.get_text(strip=True) if fraction_el else ""

            # Amazon renders the whole part with the market's thousands
            # separator: '1,299' on US/UK pages, '1.234' on EU pages. The
            # separator tells us which decimal separator to pair the fraction
            # with so '1.234' + '56' becomes '1234,56', not '1.234.56'.
            if "." in whole:
                whole = whole.replace(".", "")
                price_text = f"{whole},{frac}" if frac else whole
            else:
                price_text = f"{whole}.{frac}" if frac else whole

            symbol_el = card.select_one(".a-price-symbol")
            symbol = symbol_el.get_text(strip=True) if symbol_el else ""
            if not symbol:
                price_el = card.select_one(".a-price")
                if price_el:
                    m = re.search(r"[$£€¥₹]", price_el.get_text())
                    if m:
                        symbol = m.group(0)
            price = symbol + price_text

        # Fallback: some layouts only render the offscreen price text.
        if price is None:
            off_el = card.select_one(".a-price .a-offscreen")
            if off_el:
                off_text = off_el.get_text(strip=True)
                if off_text and re.search(r"[$£€¥₹]", off_text):
                    price = off_text

        # Extract rating (localized texts like "4,7 von 5 Sternen" are normalized)
        rating = None
        rating_el = card.select_one("i.a-icon-star, i.a-icon-star-small, span.a-icon-alt")
        if rating_el:
            rating = _normalize_rating(rating_el.get_text(strip=True))

        # Extract review count
        review_count = None
        review_el = card.select_one("span.a-size-base.s-underline-text")
        if not review_el:
            review_el = card.select_one("a.a-size-base[href*='customer-reviews']")
        if not review_el:
            review_el = card.select_one("span.a-size-base[aria-label*='ratings']")
        if review_el:
            # Strip both comma (US '1,299') and dot (EU '1.234') thousands separators
            text = review_el.get_text(strip=True).replace(",", "").replace(".", "")
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
        url=url,
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
    """Fill missing product.price via browser JS evaluation. Mutates the product in-place."""
    if not product.price:
        browser_price = _extract_price_from_browser(page)
        if browser_price:
            product.price = browser_price
            log.info("price filled from browser: %s", browser_price)
        else:
            log.info("no price found from browser or HTML")
    return product
