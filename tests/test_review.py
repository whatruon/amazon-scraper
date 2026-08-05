"""Tests for review extraction helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from scraper.review import (
    _extract_helpful_votes,
    _extract_review_from_element,
    _load_more_reviews,
)


def _element(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class TestExtractReviewFromElement:
    def test_full_review_extraction(self):
        html = """
        <div data-hook="review">
            <span data-hook="review-body"><span>Great product, works perfectly!</span></span>
            <span data-hook="review-star-rating">5.0 out of 5 stars</span>
            <span data-hook="review-date">Reviewed in the United States on January 5, 2025</span>
            <span data-hook="avp-badge">Verified Purchase</span>
            <span data-hook="helpful-vote-statement">3 people found this helpful</span>
        </div>
        """
        review = _extract_review_from_element(_element(html))
        assert review is not None
        assert review['text'] == 'Great product, works perfectly!'
        assert review['rating'] == '5.0'
        assert review['date'] == 'January 5, 2025'
        assert review['verified'] is True
        assert review['helpful_votes'] == 3

    def test_no_helpful_votes(self):
        html = """
        <div data-hook="review">
            <span data-hook="review-body"><span>Okay product.</span></span>
            <span data-hook="review-star-rating">3.0 out of 5 stars</span>
            <span data-hook="review-date">Reviewed in the United States on February 1, 2025</span>
            <span data-hook="avp-badge">Verified Purchase</span>
        </div>
        """
        review = _extract_review_from_element(_element(html))
        assert review is not None
        assert review['helpful_votes'] is None


class TestHelpfulVotes:
    def test_numeric_plural(self):
        el = _element('<span data-hook="helpful-vote-statement">3 people found this helpful</span>')
        assert _extract_helpful_votes(el) == 3

    def test_numeric_singular(self):
        el = _element('<span data-hook="helpful-vote-statement">1 person found this helpful</span>')
        assert _extract_helpful_votes(el) == 1

    def test_word_singular(self):
        el = _element('<span data-hook="helpful-vote-statement">One person found this helpful</span>')
        assert _extract_helpful_votes(el) == 1

    def test_no_statement_returns_none(self):
        el = _element('<div data-hook="review"><span data-hook="review-body"><span>x</span></span></div>')
        assert _extract_helpful_votes(el) is None


class TestLoadMoreReviews:
    def test_returns_true_even_when_wait_times_out(self):
        page = MagicMock()
        control = MagicMock()
        control.is_visible.return_value = True
        page.query_selector.return_value = control
        page.wait_for_load_state.side_effect = TimeoutError("networkidle timed out")

        assert _load_more_reviews(page) is True
        control.click.assert_called_once()

    def test_returns_false_when_no_control(self):
        page = MagicMock()
        page.query_selector.return_value = None

        assert _load_more_reviews(page) is False
