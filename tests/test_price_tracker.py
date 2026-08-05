"""Tests for price_tracker numeric parsing."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from scraper.price_tracker import (
    TrackPriceError,
    _extract_original_price,
    _to_amount,
    track_price,
)


class TestToAmount:
    def test_us_formats(self):
        assert _to_amount("$29.99") == 29.99
        assert _to_amount("1,299.99") == 1299.99
        assert _to_amount("1,000,000.99") == 1000000.99
        assert _to_amount("1000") == 1000.0
        assert _to_amount("$1,299.99") == 1299.99

    def test_eu_formats(self):
        assert _to_amount("29,99") == 29.99
        assert _to_amount("1.234,56") == 1234.56
        assert _to_amount("29,99 €") == 29.99

    def test_eu_whole_thousands(self):
        # '1.234' on an EU page is 1234 whole units, not a US-style decimal.
        assert _to_amount("1.234") == 1234.0
        assert _to_amount("2.500") == 2500.0
        assert _to_amount("12.345") == 12345.0

    def test_invalid(self):
        assert _to_amount("") is None
        assert _to_amount("free") is None
        assert _to_amount("$") is None
        assert _to_amount("1.2.3") is None

    def test_discount_computation_eu(self):
        from scraper.price_tracker import _apply_discount

        info = {"current_price": "29,99 €", "original_price": "39,99 €"}
        _apply_discount(info)
        assert info["is_on_sale"] is True
        assert info["savings_amount"] == "€10.00"
        assert info["discount_percentage"] == "25%"


class TestOriginalPriceFallback:

    def test_cdn_spaced_symbol(self):
        html = '<div class="a-text-price"><span>List Price: CDN$ 39.99</span></div>'
        assert _extract_original_price(BeautifulSoup(html, "lxml")) == "CDN$ 39.99"

    def test_eu_trailing_symbol(self):
        html = '<div class="a-text-price"><span>List Price: 1.234,56 €</span></div>'
        assert _extract_original_price(BeautifulSoup(html, "lxml")) == "1.234,56 €"

    def test_plain_us(self):
        html = '<div class="a-text-price"><span>Was: $39.99</span></div>'
        assert _extract_original_price(BeautifulSoup(html, "lxml")) == "$39.99"

    def test_no_price_text_returns_none(self):
        html = '<div class="a-text-price"><span>No deal here</span></div>'
        assert _extract_original_price(BeautifulSoup(html, "lxml")) is None


class TestTrackPrice:
    """End-to-end behavior of track_price()."""

    def test_full_flow_on_sale_with_deal(self):
        html = """
        <div id="corePrice_feature_div"><span class="a-offscreen">$29.99</span></div>
        <div id="listPrice"><span class="a-offscreen">$39.99</span></div>
        <div id="dealBadge_feature_div"><span class="dealLabel">Lightning Deal</span></div>
        """
        soup = BeautifulSoup(html, "lxml")
        info = track_price(soup=soup)

        assert info["current_price"] == "$29.99"
        assert info["original_price"] == "$39.99"
        assert info["deal_type"] == "Lightning Deal"
        assert info["is_on_sale"] is True
        assert info["savings_amount"] == "$10.00"
        assert info["discount_percentage"] == "25%"

    def test_no_deal_fields_default(self):
        html = '<div id="corePrice_feature_div"><span class="a-offscreen">$9.99</span></div>'
        info = track_price(soup=BeautifulSoup(html, "lxml"))
        assert info["current_price"] == "$9.99"
        assert info["original_price"] is None
        assert info["deal_type"] is None
        assert info["savings_amount"] is None
        assert info["is_on_sale"] is False

    def test_page_only_uses_page_content(self):
        page = MagicMock()
        page.content.return_value = (
            '<div id="corePrice_feature_div"><span class="a-offscreen">$9.99</span></div>'
        )
        info = track_price(page=page)
        assert info["current_price"] == "$9.99"
        assert info["is_on_sale"] is False

    def test_requires_page_or_soup(self):
        with pytest.raises(TrackPriceError):
            track_price()
