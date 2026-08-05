from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Selectors — organized by extraction target
#
# Naming note: selectors target three distinct anchor types, reflecting
# how Amazon exposes elements in the DOM:
#   `#id`            - single HTML element by its `id` attribute
#   `.class`         - element(s) matched by one or more CSS classes
#   `[attr=...]`     - element matched by an attribute value
# A single selector quite often combines two or more (e.g.
# `#corePrice_feature_div .a-offscreen` finds the `.a-offscreen`
# descendant of the `#corePrice_feature_div` id). `#` and `.` are not
# interchangeable styles — they match different kinds of nodes — so the
# lists keep whichever prefix(es) each selector actually needs.
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Price — CURRENT selling price (the buybox / deal price you pay)
# ------------------------------------------------------------------
PRICE_SELECTORS = [
    # Prime price display blocks
    "#corePrice_feature_div .a-offscreen",
    "#corePrice_desktop .a-offscreen",
    "#unifiedPrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .aok-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    # Accessibility / legacy layout price nodes
    "#apex-pricetopay-accessibility-label",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
]

# ------------------------------------------------------------------
# Price — "original" price (strikethrough / list price, when the item
# is on sale). Kept separate from PRICE_SELECTORS so a "current" price
# is never masked by the "was" price; `#priceblock_dealprice` belongs
# to the current-price group only.
# ------------------------------------------------------------------
ORIGINAL_PRICE_SELECTORS = [
    ".a-text-price .a-offscreen",
    "#listPrice .a-offscreen",
    "#priceblock_ourprice .a-text-price .a-offscreen",
    ".a-size-base.a-color-secondary .a-offscreen",
    '[data-testid="odal-original-price"] .a-offscreen',
    ".a-section.a-spacing.microverse .a-text-price span",
]

TITLE_SELECTORS = ["#productTitle", "title"]

RATING_SELECTORS = [
    "span[data-hook='rating-out-of-text']",
    ".a-icon-alt",
]

REVIEW_COUNT_SELECTORS = [
    "span[data-hook='total-review-count']",
    "#acrCustomerReviewText",
]

IMAGE_SELECTORS = [
    "#imgTagWrapperId img",
    "#main-image-container img",
    "#altImages img",
    ".imgTagWrapper img",
    "#landingImage",
    "#main-image",
]

IMAGE_CONTAINER_SELECTORS = [
    "#imgTagWrapperId",
    "#main-image-container",
    "#altImages",
]

AVAILABILITY_SELECTORS = [
    "#availability span",
    "#deliveryBlockMessage",
]

BRAND_SELECTORS = [
    "#bylineInfo",
    "#bylineInfo_feature_div",
    "a.brand-link",
    "a[href*='/stores/brand/']",
    "#po-brand .a-span2",
]

SELLER_SELECTORS = [
    "#bylineInfo",
    "#bylineInfo_feature_div",
    "#merchant-info",
    "#merchantInfo",
    '[data-feature-name="bylineInfo"]',
    "#byline",
    "#bylineInfo_text",
    ".tabular-buybox-text:nth-child(2) span",
]

FBA_SELECTORS = [
    "#tabular-buybox[data-csa-c-content-id='btfbb']",
    "#tabular-buybox",
]

SELLER_RATING_SELECTORS = [
    "#sellerProfileTriggerId",
    "#merchant-vars:not(:empty)",
    '[data-hook="avg-star-rating"]',
    "#avgRating",
    ".reviewCountTextLinkedHistogram",
]

SHIPS_FROM_SELECTORS = [
    "#shipsFrom",
    "#shipsFromDetail",
    ".tabular-buybox-text",
    "#deliveryBlockMessage",
    "#ubb-ufss-slot",
    "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE",
]

PRODUCT_DETAILS_SELECTORS = [
    "#productDetails_detailBullets_sections1 tr",
    "#prodDetails tr",
    "#productDetails_techSpec_section_1 tr",
]

DEAL_SELECTORS = [
    "#dealBadge_feature_div",
    "#dealBadge",
    ".dealBadge",
    '[data-hawkeye-key="mkcp.dealbadge"]',
    ".dealLabel",
    ".a-badge.aok-align-bottom",
    ".a-row.a-spacing-mini .a-color-price",
    "#saleBadge",
    ".a-row.a-size-base.a-color-price",
]

COUPON_SELECTORS = [
    ".couponBadge",
    '[data-hook="promo-price"]',
    ".a-section.couponClippableBlock",
    ".promoBadge",
]

SEARCH_RESULT_SELECTORS = [
    '[data-component-type="s-search-result"]',
]

SEARCH_TITLE_SELECTORS = [
    "h2 a.a-link-normal",
    "h2 a.a-text-normal",
    "a.a-link-normal.s-link-style",
]

SEE_ALL_REVIEWS_SELECTORS = [
    '[data-hook="see-all-reviews-link-foot"]',
    '#reviews-medley-footer a',
    '[data-hook="see-all-reviews-link"]',
    'a[data-hook="see-all-reviews-link-foot"]',
]

LOAD_MORE_REVIEWS_SELECTORS = [
    '[data-hook="see-more-reviews-link"]',
    '.a-pagination .a-last:not(.a-disabled) a',
    '[data-hook="pagination-bar"] .a-last:not(.a-disabled) a',
]

# ------------------------------------------------------------------
# Browser fingerprinting
# ------------------------------------------------------------------

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
]

TIMEZONE_LOCALE = [
    ("America/New_York", "en-US"),
    ("America/Chicago", "en-US"),
    ("America/Denver", "en-US"),
    ("America/Los_Angeles", "en-US"),
]

DOMAIN_LOCALE: dict[str, tuple[str, str]] = {
    "amazon.ae": ("Asia/Dubai", "en-AE"),
    "amazon.co.uk": ("Europe/London", "en-GB"),
    "amazon.de": ("Europe/Berlin", "de-DE"),
    "amazon.fr": ("Europe/Paris", "fr-FR"),
    "amazon.it": ("Europe/Rome", "it-IT"),
    "amazon.es": ("Europe/Madrid", "es-ES"),
    "amazon.ca": ("America/Toronto", "en-CA"),
    "amazon.co.jp": ("Asia/Tokyo", "ja-JP"),
    "amazon.in": ("Asia/Kolkata", "en-IN"),
    "amazon.com.au": ("Australia/Sydney", "en-AU"),
    "amazon.com.br": ("America/Sao_Paulo", "pt-BR"),
    "amazon.com.mx": ("America/Mexico_City", "es-MX"),
    "amazon.nl": ("Europe/Amsterdam", "nl-NL"),
    "amazon.se": ("Europe/Stockholm", "sv-SE"),
    "amazon.pl": ("Europe/Warsaw", "pl-PL"),
    "amazon.sg": ("Asia/Singapore", "en-SG"),
    "amazon.eg": ("Africa/Cairo", "en-EG"),
    "amazon.sa": ("Asia/Riyadh", "en-SA"),
    "amazon.tr": ("Europe/Istanbul", "tr-TR"),
}

# ------------------------------------------------------------------
# URL tracking params to strip
# ------------------------------------------------------------------

AMAZON_TRACKING_PARAMS = {
    "sbo", "tag", "ref", "ref_", "pf_rd_r", "pf_rd_p", "pf_rd_m",
    "pf_rd_s", "pf_rd_t", "pf_rd_i", "linkCode", "linkId", "language",
    "th", "psc", "smid", "coliid", "colid", "ie",
    "sr", "s", "qid", "crid", "sprefix", "dchild", "rh", "pf", "keywords",
}

# ------------------------------------------------------------------
# Timeouts & defaults
# ------------------------------------------------------------------

DEFAULT_TIMEOUT = 15000        # Navigation timeout (ms)
DEFAULT_RETRIES = 2            # Max retries on failure
DEFAULT_MAX_RESULTS = 5        # Max search results
DEFAULT_MAX_PAGES = 3          # Max search result pages
DEFAULT_MAX_REVIEWS = 10       # Max reviews scraped per product
DEFAULT_ZIP_CODE = "90035"
DEFAULT_CACHE_TTL = 3600       # Cache entry TTL (seconds)
MIN_IMAGE_SIZE = 200           # Minimum image dimension for filtering

# Config keys understood by load_config() — must match CLI argument dest names.
CONFIG_KEYS = {
    "retries", "timeout", "wait", "headed", "proxy", "geoip",
    "fingerprint", "persistent", "user_agent", "zip", "verbose",
    "max_results", "max_pages", "max_reviews", "cache", "cache_dir",
    "cache_ttl", "profile_dir", "domain",
}


def load_config(path: str = "config.yaml") -> dict:
    """Load a YAML config file into a dict of CLI default values.

    Returns an empty dict when the file is missing, unreadable, or contains
    no mapping — the CLI then falls back to its built-in defaults.
    """
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        log.warning("config file %s present but PyYAML is not installed; ignoring", config_path)
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        log.warning("Could not read config file %s: %s", config_path, e)
        return {}
    if not isinstance(data, dict):
        log.warning("Config file %s does not contain a mapping; ignoring", config_path)
        return {}
    return data
