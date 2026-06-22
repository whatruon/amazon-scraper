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
    # size tokens stripped -> original full-resolution images
    assert product.images[0] == "https://m.media-amazon.com/images/I/31fEv99XZ+L.jpg"
    assert product.images[1] == "https://m.media-amazon.com/images/I/61O3iMlnJIL.jpg"
    assert all("._AC_" not in u and "_US40_" not in u for u in product.images)

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


def test_price_normalizes_label_noise():
    from scraper.parser import normalize_price
    assert normalize_price("$275.00 with 5 percent off") == "$275.00"
    assert normalize_price("List: $399.99") == "$399.99"
    assert normalize_price("Currently unavailable") is None
    assert normalize_price(None) is None


def test_price_ignores_strikethrough_list_price():
    # secondary (struck-through list) price appears first; price-to-pay must win
    html = """
    <html><body><div id="corePrice_feature_div">
      <span class="a-price a-text-price" data-a-color="secondary">
        <span class="a-offscreen">$349.99</span></span>
      <span class="a-price priceToPay" data-a-color="base">
        <span class="a-offscreen">$275.00</span></span>
    </div></body></html>
    """
    assert parse_product(html).price == "$275.00"


def test_full_size_image_strips_size_tokens():
    from scraper.parser import full_size_image
    base = "https://m.media-amazon.com/images/I/61O3iMlnJIL"
    assert full_size_image(base + "._AC_SL1500_.jpg") == base + ".jpg"
    assert full_size_image(base + "._AC_US40_.jpg") == base + ".jpg"
    # video play-icon overlay thumbnail (no leading underscore)
    assert full_size_image(base + ".SS40_BG85,85,85_BR-120_PKdp-play-icon-overlay__.jpg") == base + ".jpg"
    # already full-size: unchanged
    assert full_size_image(base + ".jpg") == base + ".jpg"


def test_profile_for_url_routing():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scrapercli", Path(__file__).parent.parent / "scraper.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    profiles = [
        {"id": "ae", "name": "Amazon UAE"},
        {"id": "de", "name": "Amazon DE"},
        {"id": "uk", "name": "Amazon UK"},
        {"id": "us", "name": "Amazon US"},
    ]
    assert cli.profile_for_url("https://www.amazon.com/dp/B09XS7JWHH", profiles)[0] == "us"
    assert cli.profile_for_url("https://www.amazon.co.uk/dp/B0X", profiles)[0] == "uk"
    assert cli.profile_for_url("https://www.amazon.de/dp/B0X", profiles)[0] == "de"
    assert cli.profile_for_url("https://www.amazon.ae/dp/B0X", profiles)[0] == "ae"
    import pytest
    with pytest.raises(ValueError):
        cli.profile_for_url("https://www.amazon.fr/dp/B0X", profiles)
