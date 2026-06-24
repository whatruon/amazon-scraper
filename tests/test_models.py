"""
Tests for Product dataclass and its methods.
"""
from __future__ import annotations

import json

import pytest

from scraper.models import Product


def test_product_creation_defaults():
    """Test Product creation with default values."""
    product = Product()
    assert product.title is None
    assert product.price is None
    assert product.rating is None
    assert product.review_count is None
    assert product.images == []
    assert product.bullets == []
    assert product.availability is None
    assert product.asin is None
    assert product.brand is None
    assert product.schema_version == "1.0"
    assert product.scraped_at is None


def test_product_creation_with_values():
    """Test Product creation with provided values."""
    product = Product(
        title="Test Product",
        price="$29.99",
        rating="4.5 out of 5",
        review_count="100 ratings",
        images=["image1.jpg", "image2.jpg"],
        bullets=["Bullet 1", "Bullet 2"],
        availability="In Stock",
        asin="B0ABCDEF12",
        brand="TestBrand"
    )

    assert product.title == "Test Product"
    assert product.price == "$29.99"
    assert product.rating == "4.5 out of 5"
    assert product.review_count == "100 ratings"
    assert product.images == ["image1.jpg", "image2.jpg"]
    assert product.bullets == ["Bullet 1", "Bullet 2"]
    assert product.availability == "In Stock"
    assert product.asin == "B0ABCDEF12"
    assert product.brand == "TestBrand"
    assert product.schema_version == "1.0"
    assert product.scraped_at is None


def test_to_dict():
    """Test Product.to_dict() method."""
    product = Product(
        title="Test Product",
        price="$29.99",
        asin="B0ABCDEF12"
    )

    expected = {
        "title": "Test Product",
        "price": "$29.99",
        "rating": None,
        "review_count": None,
        "images": [],
        "bullets": [],
        "availability": None,
        "asin": "B0ABCDEF12",
        "brand": None,
        "schema_version": "1.0",
        "scraped_at": None
    }

    assert product.to_dict() == expected


def test_to_json():
    """Test Product.to_json() method."""
    product = Product(
        title="Test Product",
        price="$29.99",
        rating="4.5 out of 5",
        asin="B0ABCDEF12"
    )

    json_output = product.to_json(indent=2)
    parsed = json.loads(json_output)

    assert parsed["title"] == "Test Product"
    assert parsed["price"] == "$29.99"
    assert parsed["rating"] == "4.5 out of 5"
    assert parsed["asin"] == "B0ABCDEF12"
    assert parsed["schema_version"] == "1.0"
    assert "scraped_at" in parsed
    assert parsed["scraped_at"] is not None


def test_validate_asin_valid():
    """Test ASIN validation with valid ASINs."""
    test_cases = [
        "B0ABCDEF12",
        "1234567890",
        "ABCDEF1234",
        "0123456789",
        "A1B2C3D4E5"
    ]

    for asin in test_cases:
        product = Product(asin=asin)
        assert product.validate_asin() is True, f"ASIN {asin} should be valid"


def test_validate_asin_invalid():
    """Test ASIN validation with invalid ASINs."""
    test_cases = [
        None,
        "",
        "B0ABCDEF1",   # 9 chars
        "B0ABCDEF123", # 11 chars
        "b0abcdef12",  # lowercase
        "B0ABCDEF!@",  # special chars
        "B0ABCD EF12", # space
        "B0ABCD.EF12", # dot
    ]

    for asin in test_cases:
        product = Product(asin=asin)
        assert product.validate_asin() is False, f"ASIN '{asin}' should be invalid"


def test_validate_price_valid():
    """Test price validation with valid price formats.

    Note: Validates US-style price formatting (commas for thousands, dots for decimals).
    European prices (e.g., €29,99) are not supported by this validator.
    """
    test_cases = [
        "$29.99",
        "$29",
        "$1,299.99",
        "$0.99",
        "$1000",
        "$1,000,000.99",
        "£29.99",
        "¥2,999",
        "₹2,999.00"
    ]

    for price in test_cases:
        product = Product(price=price)
        assert product.validate_price() is True, f"Price '{price}' should be valid"


def test_validate_price_invalid():
    """Test price validation with invalid price formats."""
    test_cases = [
        None,
        "",
        "29.99",       # No currency symbol
        "$",            # Only currency symbol
        "$abc",         # Non-numeric after currency
        "$ 29.99",      # Space after currency symbol (not allowed)
        "free",         # Text
        "$29.999",      # Too many decimal places
        "$29,999,99",   # Invalid comma placement (not thousands grouping)
        "€29,99",       # European format (decimal comma, not supported)
    ]

    for price in test_cases:
        product = Product(price=price)
        assert product.validate_price() is False, f"Price '{price}' should be invalid"


def test_validate_rating_valid():
    """Test rating validation with valid rating formats."""
    test_cases = [
        "0 out of 5",
        "0.0 out of 5",
        "1 out of 5",
        "1.5 out of 5",
        "2.0 out of 5",
        "2.5 out of 5",
        "3.0 out of 5",
        "3.5 out of 5",
        "4.0 out of 5",
        "4.5 out of 5",
        "5 out of 5",
        "5.0 out of 5"
    ]

    for rating in test_cases:
        product = Product(rating=rating)
        assert product.validate_rating() is True, f"Rating '{rating}' should be valid"


def test_validate_rating_invalid():
    """Test rating validation with invalid rating formats."""
    test_cases = [
        None,
        "",
        "out of 5",        # Missing number
        "5 out of",        # Missing 5
        "5 out of 6",      # Wrong denominator
        "6 out of 5",      # Numerator > 5
        "5.5 out of 5",    # Numerator > 5 with decimal
        "abc out of 5",    # Non-numeric
        "5 out of five",   # Text instead of number
        "5.0 out of 5.0",  # Decimal in denominator
    ]

    for rating in test_cases:
        product = Product(rating=rating)
        assert product.validate_rating() is False, f"Rating '{rating}' should be invalid"


def test_validate_methods_with_none_values():
    """Test validation methods when fields are None."""
    product = Product()

    assert product.validate_asin() is False
    assert product.validate_price() is False
    assert product.validate_rating() is False


def test_product_from_parser_integration():
    """Test Product creation mimics what parser.py does."""
    # This mimics the parse_product function in parser.py
    # Note: ASIN must be exactly 10 characters
    product = Product(
        title="Test Product Title",
        price="$29.99",
        rating="4.5 out of 5",
        review_count="100 ratings",
        images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        bullets=["Feature 1", "Feature 2", "Feature 3"],
        availability="In Stock",
        asin="B0TESTPROD".upper()  # Make sure ASIN is uppercase and exactly 10 chars
    )

    # All validation should pass
    assert product.validate_asin() is True
    assert product.validate_price() is True
    assert product.validate_rating() is True

    # to_json should work
    json_str = product.to_json()
    parsed = json.loads(json_str)
    assert parsed["title"] == "Test Product Title"
    assert parsed["price"] == "$29.99"
    assert len(parsed["images"]) == 2
    assert len(parsed["bullets"]) == 3