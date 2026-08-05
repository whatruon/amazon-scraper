"""Tests for seller extraction helpers."""
from __future__ import annotations

from bs4 import BeautifulSoup

from scraper.seller import (
    _extract_ships_from,
    _is_buybox_owner,
    _is_fulfilled_by_amazon,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class TestBuyboxOwner:
    def test_matching_seller_owns_buybox(self):
        html = """
        <div id="buybox"><span>Sold by: Acme Inc.</span></div>
        <span id="bylineInfo">Acme Inc</span>
        """
        assert _is_buybox_owner(_soup(html)) is True

    def test_competitor_in_buybox_means_not_owner(self):
        html = """
        <div id="buybox"><span>Sold by: Competitor Co.</span></div>
        <span id="bylineInfo">Acme Inc</span>
        """
        assert _is_buybox_owner(_soup(html)) is False

    def test_sold_by_amazon_means_owner(self):
        html = """
        <div id="buybox"><a>Sold by Amazon</a></div>
        """
        assert _is_buybox_owner(_soup(html)) is True

    def test_labeled_sold_by_with_separate_link(self):
        html = """
        <div id="buybox">
            <span class="tabular-buybox-text">Sold by</span>
            <a>Acme Inc</a>
        </div>
        <span id="bylineInfo">Acme Inc</span>
        """
        assert _is_buybox_owner(_soup(html)) is True


class TestFulfilledByAmazon:
    def test_fba_outside_buybox_is_ignored(self):
        html = """
        <div id="buybox"><span>Sold by Acme Inc</span></div>
        <div class="reviews-section"><span>Fulfilled by Amazon</span></div>
        """
        assert _is_fulfilled_by_amazon(_soup(html)) is False

    def test_fba_inside_buybox(self):
        html = """
        <div id="buybox"><span>Fulfilled by Amazon</span></div>
        """
        assert _is_fulfilled_by_amazon(_soup(html)) is True


class TestShipsFrom:
    def test_ships_from_read_from_buybox_only(self):
        html = """
        <div id="buybox"><span>Ships from: China</span></div>
        <div class="reviews-section"><span>Ships from: Japan</span></div>
        """
        assert _extract_ships_from(_soup(html)) == "China"

    def test_ships_from_outside_buybox_ignored(self):
        html = """
        <div id="buybox"><span>No shipping info here</span></div>
        <div class="reviews-section"><span>Ships from: Japan</span></div>
        """
        assert _extract_ships_from(_soup(html)) is None
