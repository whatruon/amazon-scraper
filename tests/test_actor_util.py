# noqa: INP001 - tests are an implicit namespace package by design
"""Tests for the Apify actor's pure helpers (no platform imports)."""
from __future__ import annotations

from src.actor_util import (
    AMAZON_DOMAINS,
    DEFAULT_INPUT,
    domain_for_urls,
    extract_asin,
    normalize_input,
    resolve_mode,
)


def test_normalize_input_defaults_for_none():
    out = normalize_input(None)
    assert out == DEFAULT_INPUT


def test_normalize_input_empty_dict():
    out = normalize_input({})
    assert out["searchTerm"] is None
    assert out["domain"] == "amazon.com"
    assert out["maxResults"] == 5


def test_normalize_input_coerces_numeric_strings():
    out = normalize_input({"maxResults": "10", "retries": "3", "timeout": "20000", "wait": "500"})
    assert out["maxResults"] == 10
    assert out["retries"] == 3
    assert out["timeout"] == 20000
    assert out["wait"] == 500


def test_normalize_input_clamps_minima():
    out = normalize_input({"maxResults": 0, "retries": 0, "timeout": 100})
    assert out["maxResults"] == 1
    assert out["retries"] == 1
    assert out["timeout"] == 3000


def test_normalize_input_max_reviews():
    assert normalize_input({"maxReviews": "25"})["maxReviews"] == 25
    assert normalize_input({"maxReviews": 0})["maxReviews"] == 0
    assert normalize_input({"maxReviews": -5})["maxReviews"] == 0


def test_normalize_input_bad_numeric_falls_back_to_default():
    out = normalize_input({"maxResults": "abc"})
    assert out["maxResults"] == DEFAULT_INPUT["maxResults"]


def test_normalize_input_invalid_domain_reset():
    out = normalize_input({"domain": "example.com"})
    assert out["domain"] == "amazon.com"


def test_normalize_input_product_urls_string_split():
    out = normalize_input({"productUrls": "https://a/dp/X\nhttps://b/dp/Y\n"})
    assert out["productUrls"] == ["https://a/dp/X", "https://b/dp/Y"]


def test_normalize_input_keeps_none_fields_out():
    out = normalize_input({"searchTerm": None, "productUrls": None})
    assert out["searchTerm"] is None
    assert out["productUrls"] is None


def test_extract_asin():
    assert extract_asin("https://www.amazon.com/dp/B0ABCDEF12?th=1") == "B0ABCDEF12"
    assert extract_asin("https://www.amazon.co.uk/gp/product/b012345678/") == "B012345678"
    assert extract_asin("https://example.com/not-amazon") is None
    assert extract_asin("") is None


def test_domain_for_urls():
    urls = ["https://www.amazon.de/dp/B0ABCDEF12", "https://www.amazon.de/dp/B0XXXX1234"]
    assert domain_for_urls(urls) == "amazon.de"
    assert domain_for_urls(["https://example.com/x"]) is None
    assert domain_for_urls([]) is None


def test_resolve_mode_prefers_search():
    assert resolve_mode({"searchTerm": "x", "productUrls": ["https://a"]}) == "search"
    assert resolve_mode({"searchTerm": "x"}) == "search"


def test_resolve_mode_urls():
    assert resolve_mode({"productUrls": ["https://a/dp/X"]}) == "urls"


def test_resolve_mode_defaults_to_search():
    assert resolve_mode({}) == "search"


def test_amazon_domains_are_wellformed():
    for domain in AMAZON_DOMAINS:
        assert domain.startswith("amazon.")
        assert " " not in domain


def test_normalize_input_clamps_maxima():
    out = normalize_input(
        {
            "maxResults": 500,
            "maxPages": 50,
            "maxReviews": 1000,
            "retries": 99,
            "timeout": 999999,
            "wait": 99999,
        }
    )
    assert out["maxResults"] == 200
    assert out["maxPages"] == 20
    assert out["maxReviews"] == 200
    assert out["retries"] == 10
    assert out["timeout"] == 120000
    assert out["wait"] == 30000


def test_normalize_input_clamped_maxima_still_apply_minima():
    # In-bounds values are untouched; min bounds still hold.
    out = normalize_input({"maxResults": 200, "maxPages": 20, "wait": 30000})
    assert out["maxResults"] == 200
    assert out["maxPages"] == 20
    assert out["wait"] == 30000


def test_normalize_input_product_urls_non_string_items():
    out = normalize_input({"productUrls": [123, "https://a/dp/X", None, 45.6]})
    assert out["productUrls"] == ["123", "https://a/dp/X", "45.6"]


def test_amazon_domains_include_new_markets():
    for domain in ("amazon.ae", "amazon.eg", "amazon.sa", "amazon.tr"):
        assert domain in AMAZON_DOMAINS


def test_normalize_input_keeps_new_domains():
    for domain in ("amazon.ae", "amazon.eg", "amazon.sa", "amazon.tr"):
        assert normalize_input({"domain": domain})["domain"] == domain
