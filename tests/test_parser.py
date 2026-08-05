from pathlib import Path
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from scraper.parser import extract_price, parse_product

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sony_xm5():
    html = (FIXTURES / "sony_xm5.html").read_text(encoding="utf-8")
    product = parse_product(html, url="https://www.amazon.com/dp/B09XS7JWHH")

    assert product.title == "Sony WH-1000XM5 Wireless Headphones"
    assert product.price == "$275.00"
    assert product.rating == "4.2 out of 5"
    assert product.review_count == "19665"
    assert product.asin == "B09XS7JWHH"
    assert product.availability == "In Stock"

    # SX679 is the same base image as SL1500 under a different size marker,
    # so the dedup keeps only the largest variant.
    assert len(product.images) == 1
    assert product.images[0] == "https://m.media-amazon.com/images/I/61O3iMlnJIL._AC_SL1500_.jpg"

    assert len(product.bullets) == 2
    assert product.bullets[0] == "Premium noise cancellation technology"
    assert product.bullets[1] == "30-hour battery life"


def test_parse_lenovo_legion():
    html = (FIXTURES / "lenovo_legion.html").read_text(encoding="utf-8")
    product = parse_product(html, url="https://www.amazon.com/Lenovo-Legion-Tower-Gaming-Desktop/dp/B0H1DXZ1VC")

    assert product.title == "Lenovo Legion Tower 7i Gen 10 Gaming Desktop"
    assert product.price == "$6,299.00"
    assert product.rating == "5 out of 5"
    assert product.review_count == "1"
    assert product.asin == "B0H1DXZ1VC"
    assert product.availability == "In Stock"
    assert len(product.images) == 1
    assert product.images[0] == "https://m.media-amazon.com/images/I/81A7H1s3bJL._AC_SL1500_.jpg"
    assert len(product.bullets) == 3


def test_parse_no_price_html():
    html = """
    <html><body>
      <div id="productTitle">No Price Product</div>
      <span data-hook="rating-out-of-text">3.0 out of 5</span>
      <span data-hook="total-review-count">100 ratings</span>
    </body></html>
    """
    product = parse_product(html)
    assert product.title == "No Price Product"
    assert product.price is None
    assert product.rating == "3.0 out of 5"
    assert product.review_count == "100"


def test_extract_asin_gp_product():
    html = "<html><body></body></html>"
    product = parse_product(html, url="https://www.amazon.com/gp/product/B0ABCDE123")
    assert product.asin == "B0ABCDE123"


def test_extract_asin_from_meta():
    html = '<html><head><meta name="asin" content="X00TEST123" /></head><body></body></html>'
    product = parse_product(html)
    assert product.asin == "X00TEST123"


def test_extract_asin_from_input():
    html = '<html><body><input name="ASIN" value="Z99TEST456" /></body></html>'
    product = parse_product(html)
    assert product.asin == "Z99TEST456"


def test_bullet_dedup():
    html = """
    <html><body>
    <div id="feature-bullets">
      <ul>
        <li><span>Feature One</span></li>
        <li><span>Feature Two</span></li>
        <li><span>feature one</span></li>
      </ul>
    </div>
    </body></html>
    """
    product = parse_product(html)
    assert len(product.bullets) == 2
    assert product.bullets[0] == "Feature One"
    assert product.bullets[1] == "Feature Two"


# ------------------------------------------------------------------
# Availability extraction edge cases
# ------------------------------------------------------------------

def test_availability_empty_span_returns_none():
    """Empty <span> inside #availability should yield None, not ''."""
    html = '<html><body><div id="availability"><span>  </span></div></body></html>'
    product = parse_product(html)
    assert product.availability is None


def test_availability_no_element_returns_none():
    """No availability elements at all should yield None."""
    html = '<html><body><div>no availability here</div></body></html>'
    product = parse_product(html)
    assert product.availability is None


def test_availability_delivery_block():
    """Fallback to #deliveryBlockMessage when #availability lacks a span."""
    html = '<html><body><div id="deliveryBlockMessage">FREE delivery Dec 24</div></body></html>'
    product = parse_product(html)
    assert product.availability == "FREE delivery Dec 24"


def test_parse_localized_rating_german():
    """amazon.de renders '4,7 von 5 Sternen' — must normalize to '4.7 out of 5'."""
    html = "<html><body><span data-hook='rating-out-of-text'>4,7 von 5 Sternen</span></body></html>"
    product = parse_product(html)
    assert product.rating == "4.7 out of 5"
    assert product.validate_rating()


def test_parse_localized_rating_two_decimal_german():
    """'4,70 von 5 Sternen' must normalize to one decimal that validates."""
    html = "<html><body><span data-hook='rating-out-of-text'>4,70 von 5 Sternen</span></body></html>"
    product = parse_product(html)
    assert product.rating == "4.7 out of 5"
    assert product.validate_rating()


def test_parse_localized_rating_french():
    """amazon.fr renders '4,7 sur 5 étoiles'."""
    html = "<html><body><span data-hook='rating-out-of-text'>4,7 sur 5 étoiles</span></body></html>"
    product = parse_product(html)
    assert product.rating == "4.7 out of 5"
    assert product.validate_rating()


def test_parse_rating_english_unchanged():
    html = "<html><body><span data-hook='rating-out-of-text'>4.5 out of 5 stars</span></body></html>"
    product = parse_product(html)
    assert product.rating == "4.5 out of 5"
    assert product.validate_rating()


def test_parse_rating_garbage_returns_none():
    html = "<html><body><span data-hook='rating-out-of-text'>Not a rating</span></body></html>"
    product = parse_product(html)
    assert product.rating is None


def test_extract_price_prefers_static_html():
    """Static HTML wins; the browser is never consulted when it has a price."""
    page = MagicMock()
    soup = BeautifulSoup(
        '<div id="corePrice_feature_div"><span class="a-offscreen">$12.50</span></div>',
        "lxml",
    )
    assert extract_price(soup, page) == "$12.50"
    page.evaluate.assert_not_called()


def test_extract_price_uses_browser_when_soup_empty():
    """extract_price falls back to JS evaluation when static HTML has no price."""
    page = MagicMock()
    page.evaluate.return_value = "$29.99"
    soup = BeautifulSoup("<html><body><div>no price here</div></body></html>", "lxml")
    assert extract_price(soup, page) == "$29.99"
    page.evaluate.assert_called_once()


def test_extract_price_browser_failure_returns_none():
    """A JS evaluation failure must degrade gracefully to None."""
    page = MagicMock()
    page.evaluate.side_effect = RuntimeError("js boom")
    soup = BeautifulSoup("<html><body><div>no price here</div></body></html>", "lxml")
    assert extract_price(soup, page) is None
