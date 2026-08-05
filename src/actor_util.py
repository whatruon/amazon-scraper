"""Pure helpers for the Apify actor — no platform imports, fully unit-testable."""
from __future__ import annotations

import re
from urllib.parse import urlparse

AMAZON_DOMAINS = [
    "amazon.com",
    "amazon.ae",
    "amazon.co.uk",
    "amazon.de",
    "amazon.fr",
    "amazon.it",
    "amazon.es",
    "amazon.ca",
    "amazon.co.jp",
    "amazon.in",
    "amazon.com.au",
    "amazon.com.br",
    "amazon.com.mx",
    "amazon.nl",
    "amazon.se",
    "amazon.pl",
    "amazon.sg",
    "amazon.eg",
    "amazon.sa",
    "amazon.tr",
]

DEFAULT_INPUT = {
    "searchTerm": None,
    "productUrls": None,
    "domain": "amazon.com",
    "maxResults": 5,
    "maxPages": 3,
    "maxReviews": 10,
    "zip": "90035",
    "proxy": {"useApifyProxy": True},
    "session": None,
    "retries": 2,
    "timeout": 15000,
    "wait": 0,
    "verbose": False,
    "freshRun": False,
}

_MAX_BOUNDS = {
    "maxResults": 200,
    "maxPages": 20,
    "maxReviews": 200,
    "retries": 10,
    "timeout": 120000,
    "wait": 30000,
}

_ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/)([A-Z0-9]{10})", re.IGNORECASE)


def normalize_input(raw: dict | None) -> dict:
    """Fill in defaults and coerce types from the raw Actor input dict."""
    if not isinstance(raw, dict):
        raw = {}
    out = dict(DEFAULT_INPUT)
    for key, value in raw.items():
        if value is None:
            continue
        out[key] = value

    for name in ("maxResults", "maxPages", "maxReviews", "retries", "timeout", "wait"):
        if isinstance(out[name], str):
            try:
                out[name] = int(out[name])
            except (TypeError, ValueError):
                out[name] = DEFAULT_INPUT[name]

    out["maxResults"] = max(1, int(out["maxResults"]))
    out["maxPages"] = max(1, int(out["maxPages"]))
    out["maxReviews"] = max(0, int(out["maxReviews"]))
    out["retries"] = max(1, int(out["retries"]))
    out["timeout"] = max(3000, int(out["timeout"]))
    out["wait"] = max(0, int(out["wait"]))

    for name, upper in _MAX_BOUNDS.items():
        out[name] = min(upper, int(out[name]))

    if out["searchTerm"] is not None:
        out["searchTerm"] = str(out["searchTerm"]).strip() or None
    if out["productUrls"] is not None:
        if isinstance(out["productUrls"], str):
            out["productUrls"] = [u.strip() for u in out["productUrls"].splitlines() if u.strip()]
        out["productUrls"] = [
            str(u).strip() for u in out["productUrls"] if u is not None and str(u).strip()
        ]

    out["zip"] = str(out["zip"])
    if out["domain"] not in AMAZON_DOMAINS:
        out["domain"] = DEFAULT_INPUT["domain"]
    return out


def extract_asin(url: str) -> str | None:
    """Return the ASIN embedded in an Amazon URL, if any."""
    match = _ASIN_RE.search(url or "")
    return match.group(1).upper() if match else None


def domain_for_urls(urls: list[str]) -> str | None:
    """Return the amazon domain implied by the first recognizable product URL."""
    for url in urls or []:
        host = (urlparse(url).netloc or "").lower()
        for domain in AMAZON_DOMAINS:
            if host == domain or host.endswith("." + domain):
                return domain
    return None


def resolve_mode(inp: dict) -> str:
    """Decide the run mode: 'search' (searchTerm) or 'urls' (productUrls).

    When both are provided, the search term takes precedence.
    """
    if inp.get("searchTerm"):
        return "search"
    if inp.get("productUrls"):
        return "urls"
    return "search"
