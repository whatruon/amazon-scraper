from __future__ import annotations

# ------------------------------------------------------------------
# Selectors — organized by extraction target
# ------------------------------------------------------------------

PRICE_SELECTORS = [
    "#corePrice_feature_div .a-offscreen",
    "#corePrice_desktop .a-offscreen",
    "#unifiedPrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .aok-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#apex-pricetopay-accessibility-label",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
]

ORIGINAL_PRICE_SELECTORS = [
    ".a-text-price .a-offscreen",
    "#listPrice .a-offscreen",
    "#priceblock_ourprice .a-text-price .a-offscreen",
    ".a-size-base.a-color-secondary .a-offscreen",
    '[data-testid="odal-original-price"] .a-offscreen',
    ".a-section.a-spacing.microverse .a-text-price span",
    "#priceblock_dealprice",
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
    "#shippingMethod",
    "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE",
    "#deliveryBlockMessage",
]

SELLER_RATING_SELECTORS = [
    "#sellerProfileTriggerId",
    "#merchant-vars:not(:empty)",
    '[data-hook="avg-star-rating"]',
    "#avgRating",
    ".reviewCountTextLinkedHistogram",
]

SELLER_BUYBOX_SELECTORS = [
    "#buybox-see-all-buying-choices",
    "#buybox",
    "#BuyBox",
    "#mbc",
    "#merchant-info",
    "#merchantDetails",
]

SELLER_PROMINENT_SELECTORS = [
    "#btfbb",
    "#merchant-info",
    "#merchantInfo",
    "#mir-layout-DELIVERY_BLOCK",
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

CATEGORY_SELECTORS = [
    "#breadcrumb ul",
    "#wayfinding-breadcrumbs_feature_div ul",
    ".a-breadcrumb",
]

VARIANT_SELECTORS = [
    "#variation_color_name li",
    "#variation_size_name li",
    "#variation_style_name li",
    "#variation_length li",
    ".twisterSwatch",
    "li[data-asin]",
    "li[data-defaultasin]",
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
    "amazon.ae": ("Asia/Dubai", "en-US"),
    "amazon.co.uk": ("Europe/London", "en-US"),
    "amazon.de": ("Europe/Berlin", "en-US"),
    "amazon.fr": ("Europe/Paris", "en-US"),
    "amazon.it": ("Europe/Rome", "en-US"),
    "amazon.es": ("Europe/Madrid", "en-US"),
    "amazon.ca": ("America/Toronto", "en-US"),
    "amazon.co.jp": ("Asia/Tokyo", "en-US"),
    "amazon.in": ("Asia/Kolkata", "en-US"),
    "amazon.com.au": ("Australia/Sydney", "en-US"),
    "amazon.com.br": ("America/Sao_Paulo", "en-US"),
    "amazon.com.mx": ("America/Mexico_City", "en-US"),
    "amazon.nl": ("Europe/Amsterdam", "en-US"),
    "amazon.se": ("Europe/Stockholm", "en-US"),
    "amazon.pl": ("Europe/Warsaw", "en-US"),
    "amazon.sg": ("Asia/Singapore", "en-US"),
    "amazon.eg": ("Africa/Cairo", "en-US"),
    "amazon.sa": ("Asia/Riyadh", "en-US"),
    "amazon.tr": ("Europe/Istanbul", "en-US"),
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
DEFAULT_WAIT = 1500            # Extra wait after page load (ms)
DEFAULT_ZIP_CODE = "90035"
DEFAULT_CACHE_TTL = 3600       # Cache entry TTL (seconds)
MIN_IMAGE_SIZE = 200           # Minimum image dimension for filtering
PARSE_TIMEOUT = 5              # Seconds before parsing is aborted
