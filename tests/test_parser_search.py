"""Tests for search results parsing functionality."""  # noqa: INP001
from __future__ import annotations

from scraper.models import Product
from scraper.parser import parse_search_card, parse_search_results


def test_parse_search_results_with_results():
    """Test parsing search results with valid product links."""
    html = """
    <html>
    <body>
        <div data-component-type="s-search-result">
            <h2>
                <a class="a-link-normal s-no-outline" href="/dp/B0074BW614">
                    <span>Sony MDR7506 Professional Headphone</span>
                </a>
            </h2>
        </div>
        <div data-component-type="s-search-result">
            <h2>
                <a class="a-link-normal s-no-outline" href="/dp/B0B9PXH6B2">
                    <span>Sony WH-CH720N Noise Cancelling Wireless Headphones</span>
                </a>
            </h2>
        </div>
    </body>
    </html>
    """
    urls = parse_search_results(html)
    assert len(urls) == 2
    assert "https://www.amazon.com/dp/B0074BW614" in urls
    assert "https://www.amazon.com/dp/B0B9PXH6B2" in urls


def test_parse_search_results_empty():
    """Test parsing search results with no results."""
    html = """
    <html>
    <body>
        <div>No search results here</div>
    </body>
    </html>
    """
    urls = parse_search_results(html)
    assert urls == []


def test_parse_search_results_deduplication():
    """Test that duplicate URLs are removed."""
    html = """
    <html>
    <body>
        <div data-component-type="s-search-result">
            <h2>
                <a class="a-link-normal s-no-outline" href="/dp/B0074BW614">
                    <span>Sony MDR7506 Professional Headphone</span>
                </a>
            </h2>
        </div>
        <div data-component-type="s-search-result">
            <h2>
                <a class="a-link-normal s-no-outline" href="/dp/B0074BW614">
                    <span>Sony MDR7506 Professional Headphone</span>
                </a>
            </h2>
        </div>
    </body>
    </html>
    """
    urls = parse_search_results(html)
    assert len(urls) == 1
    assert urls[0] == "https://www.amazon.com/dp/B0074BW614"


def test_parse_search_results_url_cleaning():
    """Test that tracking parameters are stripped from URLs."""
    html = """
    <html>
    <body>
        <div data-component-type="s-search-result">
            <h2>
                <a class="a-link-normal s-no-outline" href="/dp/B0074BW614?ref=sr_1_1&th=1">
                    <span>Sony MDR7506 Professional Headphone</span>
                </a>
            </h2>
        </div>
    </body>
    </html>
    """
    urls = parse_search_results(html)
    assert len(urls) == 1
    assert urls[0] == "https://www.amazon.com/dp/B0074BW614"


def test_parse_search_results_from_fixture():
    """Test parsing search results from the fixture file.

    Note: The parser only extracts URLs containing '/dp/' in the path.
    Non-dp links and links without product pages are excluded.
    Tracking query params are only stripped when they start with '?'.
    """
    html = """
    <html>
    <body>
        <div data-component-type="s-search-result">
            <h2 class="a-size-mini a-spacing-none a-color-base s-line-clamp-2">
                <a class="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal"
                   href="/dp/B0074BW614?ref=sr_1_1&qid=1678886400&s=electronics&sr=1-1">
                    <span class="a-size-medium a-color-base a-text-normal">
                        Sony MDR7506 Professional Large Diaphragm Headphone
                    </span>
                </a>
            </h2>
            <div class="a-row a-size-small">
                <span aria-label="4.7 out of 5 stars" class="a-icon-alt">4.7 out of 5 stars</span>
                <span class="a-size-base s-underline-text">15,000</span>
            </div>
            <div class="a-row a-spacing-micro">
                <span class="a-price" data-a-size="xl">
                    <span class="a-offscreen">$99.99</span>
                </span>
            </div>
        </div>
        <div data-component-type="s-search-result">
            <h2 class="a-size-mini a-spacing-none a-color-base s-line-clamp-2">
                <a class="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal"
                   href="/dp/B0B9PXH6B2?ref=sr_1_2&qid=1678886400&s=electronics&sr=1-2">
                    <span class="a-size-medium a-color-base a-text-normal">
                        Sony WH-CH720N Noise Cancelling Wireless Headphones
                    </span>
                </a>
            </h2>
            <div class="a-row a-size-small">
                <span aria-label="4.4 out of 5 stars" class="a-icon-alt">4.4 out of 5 stars</span>
                <span class="a-size-base s-underline-text">2,500</span>
            </div>
            <div class="a-row a-spacing-micro">
                <span class="a-price" data-a-size="xl">
                    <span class="a-offscreen">$148.00</span>
                </span>
            </div>
        </div>
        <div data-component-type="s-search-result">
            <h2 class="a-size-mini a-spacing-none a-color-base s-line-clamp-2">
                <a class="a-link-normal a-text-normal" href="/some/other/path/B0CDEFGHIJ">
                    <span class="a-size-medium a-color-base a-text-normal">Some other product (non-dp link)</span>
                </a>
            </h2>
        </div>
        <div data-component-type="s-search-result">
            <!-- No link to product page -->
            <h2 class="a-size-mini a-spacing-none a-color-base s-line-clamp-2">
                <span class="a-size-medium a-color-base a-text-normal">Product with no link</span>
            </h2>
        </div>
        <div class="a-section a-spacing-none s-result-item s-flex-full-width s-widget">
            <a class="s-pagination-item s-pagination-next" href="/s?k=sony+headphones&page=2">Next page</a>
        </div>
    </body>
    </html>
    """
    urls = parse_search_results(html)
    # Only URLs with /dp/ in the path are extracted
    assert len(urls) == 2
    assert "https://www.amazon.com/dp/B0074BW614" in urls
    assert "https://www.amazon.com/dp/B0B9PXH6B2" in urls


def _card_html(price_markup: str, href: str = "/dp/B0XWXYZDE1") -> str:
    return f"""
    <html><body>
        <div data-component-type="s-search-result">
            <h2><a class="a-link-normal" href="{href}"><span>T</span></a></h2>
            {price_markup}
        </div>
    </body></html>
    """


def test_parse_search_card_price_us_format():
    """US markup: whole '1,299' + fraction '99' -> '1,299.99'."""
    html = _card_html(
        '<div class="a-price"><span class="a-price-symbol">$</span>'
        '<span class="a-price-whole">1,299</span>'
        '<span class="a-price-fraction">99</span></div>'
    )
    price = parse_search_card(html)[0].price
    assert price == "$1,299.99"
    assert Product(price=price).validate_price()


def test_parse_search_card_price_eu_format():
    """EU (amazon.de): whole '1.234' + fraction '56' must NOT yield '1.234.56'."""
    html = _card_html(
        '<div class="a-price"><span class="a-price-symbol">€</span>'
        '<span class="a-price-whole">1.234</span>'
        '<span class="a-price-fraction">56</span></div>'
    )
    result = parse_search_card(html, domain="amazon.de")[0]
    assert result.price == "€1234,56"
    assert Product(price=result.price).validate_price()


def test_parse_search_card_price_eu_whole_number():
    """EU price with no fraction (whole 1.234 with EU thousands)."""
    html = _card_html(
        '<div class="a-price"><span class="a-price-symbol">€</span>'
        '<span class="a-price-whole">1.234</span></div>'
    )
    price = parse_search_card(html, domain="amazon.de")[0].price
    assert price == "€1234"
    assert Product(price=price).validate_price()


def test_parse_search_card_strips_path_ref():
    """Path refs (/dp/ASIN/ref=sr_1_1) must be stripped like query refs."""
    html = _card_html("", href="/dp/B0XWXYZDE1/ref=sr_1_1?qid=1678886400&th=1")
    result = parse_search_card(html)[0]
    assert result.url == "https://www.amazon.com/dp/B0XWXYZDE1"
    assert result.asin == "B0XWXYZDE1"


def test_parse_search_card_price_from_offscreen_fallback():
    """Cards that only render .a-offscreen must still yield a price."""
    html = _card_html('<div class="a-price"><span class="a-offscreen">$148.00</span></div>')
    price = parse_search_card(html)[0].price
    assert price == "$148.00"
    assert Product(price=price).validate_price()


def test_parse_search_card_localized_rating_and_count():
    """EU localized rating ('4,7 von 5 Sternen') and dot-thousands count normalize."""
    html = _card_html(
        '<span class="a-icon-alt">4,7 von 5 Sternen</span>'
        '<span class="a-size-base s-underline-text">1.234</span>'
    )
    result = parse_search_card(html, domain="amazon.de")[0]
    assert result.rating == "4.7 out of 5"
    assert result.review_count == "1234"
