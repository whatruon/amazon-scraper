from pathlib import Path

from scraper.parser import parse_product

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sony_xm5():
    html = (FIXTURES / "sony_xm5.html").read_text(encoding="utf-8")
    product = parse_product(html, url="https://www.amazon.com/dp/B09XS7JWHH")

    assert product.title == "Sony WH-1000XM5 Wireless Headphones"
    assert product.price == "$275.00"
    assert product.rating == "4.2 out of 5"
    assert product.review_count == "19,665 global ratings"
    assert product.asin == "B09XS7JWHH"
    assert product.availability == "In Stock"

    assert len(product.images) == 3
    assert product.images[0] == "https://m.media-amazon.com/images/I/31fEv99XZ+L._AC_US40_.jpg"
    assert "SL1500" in product.images[1]

    assert len(product.bullets) == 2
    assert product.bullets[0] == "Premium noise cancellation technology"
    assert product.bullets[1] == "30-hour battery life"


def test_parse_lenovo_legion():
    html = (FIXTURES / "lenovo_legion.html").read_text(encoding="utf-8")
    product = parse_product(html, url="https://www.amazon.com/Lenovo-Legion-Tower-Gaming-Desktop/dp/B0H1DXZ1VC")

    assert product.title == "Lenovo Legion Tower 7i Gen 10 Gaming Desktop"
    assert product.price == "$6,299.00"
    assert product.rating == "5 out of 5"
    assert product.review_count == "1 global rating"
    assert product.asin == "B0H1DXZ1VC"
    assert product.availability == "In Stock"
    assert len(product.images) == 1
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
    assert product.review_count == "100 ratings"


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
