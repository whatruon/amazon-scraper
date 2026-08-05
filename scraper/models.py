from __future__ import annotations

import dataclasses
import json
import re
from datetime import UTC, datetime


@dataclasses.dataclass
class SearchResult:
    """Structured data from a search-results page card."""

    url: str
    asin: str | None = None
    title: str | None = None
    price: str | None = None
    rating: str | None = None
    review_count: str | None = None
    is_prime: bool = False


@dataclasses.dataclass
class Variant:
    """Product variant (color, size, style, etc.)."""

    asin: str
    label: str | None = None
    price: str | None = None
    is_selected: bool = False


@dataclasses.dataclass
class Product:
    url: str | None = None
    title: str | None = None
    price: str | None = None
    rating: str | None = None
    review_count: str | None = None
    images: list[str] = dataclasses.field(default_factory=list)
    bullets: list[str] = dataclasses.field(default_factory=list)
    availability: str | None = None
    asin: str | None = None
    brand: str | None = None

    # Product details
    model_number: str | None = None
    date_first_available: str | None = None
    manufacturer: str | None = None
    item_weight: str | None = None
    dimensions: str | None = None
    department: str | None = None
    best_sellers_rank: str | None = None

    # Categorization
    category_path: str | None = None

    # Variants
    variants: list[Variant] = dataclasses.field(default_factory=list)

    # Seller / buy box
    seller_name: str | None = None
    fulfilled_by_amazon: bool = False
    seller_rating: str | None = None
    seller_rating_count: str | None = None
    buybox_owner: bool = False
    ships_from: str | None = None

    # Price / deal tracking
    original_price: str | None = None
    discount_percentage: str | None = None
    deal_type: str | None = None
    is_on_sale: bool = False
    savings_amount: str | None = None

    # Reviews
    reviews: list[dict] = dataclasses.field(default_factory=list)

    # Metadata
    schema_version: str = "1.0"
    scraped_at: str | None = None
    from_cache: bool = False

    # Tracks how each field was extracted (e.g. "css: #productTitle", "url_regex", None)
    extraction_quality: dict = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        if self.scraped_at is None:
            # Stamp once and reuse so repeated serializations are identical.
            self.scraped_at = datetime.now(UTC).isoformat()
        return dataclasses.asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def validate_asin(self) -> bool:
        """Validate ASIN format (10 alphanumeric characters, case-insensitive)."""
        if not self.asin:
            return False
        # Case-insensitive: accept both uppercase and lowercase ASINs.
        return bool(re.match(r"^[a-zA-Z0-9]{10}$", self.asin))

    def validate_price(self) -> bool:
        """Validate price format (currency symbol followed by number with optional separators).

        Supports multiple currencies and both comma (EUR/DE) and dot (US/UK) decimal separators.
        Handles common international price formats including those with thousand separators.
        """
        if not self.price:
            return False

        price = self.price.strip()
        if not price:
            return False

        # Optional currency symbol (prefix or suffix, with various common symbols)
        symbols = (
            "US$", "MX$", "R$", "A$", "C$", "S$", "HK$", "CDN$", "$", "£",
            "€", "¥", "₹", "₩", "₽", "zł", "Rp", "RM",
        )
        leading_symbol = None
        trailing_symbol = None

        for sym in symbols:
            if price.startswith(sym) and leading_symbol is None:
                leading_symbol = sym
            if price.endswith(sym) and trailing_symbol is None:
                trailing_symbol = sym

        # Require exactly one currency marker
        if (leading_symbol is None) == (trailing_symbol is None):
            return False

        if leading_symbol is not None:
            body = price[len(leading_symbol):]
            # Allow surrounding whitespace; Amazon renders e.g. 'CDN$ 1,299.99'.
            body = body.strip()
            # Leading symbol must be followed by a digit (no 'free').
            if not body or not body[0].isdigit():
                return False
        elif trailing_symbol is not None:
            body = price[: -len(trailing_symbol)].strip()
            # Trailing symbol may be space-separated (e.g. '29,99 €').
            if not body or not body[-1].isdigit():
                return False

        # Numeric core. Accepts:
        #   US thousands + decimal: 1,299.99 / 1,000,000.99
        #   plain decimal:           29.99 / 0.99 / 1000
        #   EU thousands + decimal:  1.234,56
        #   EU plain decimal:        29,99
        # A 3-digit group after '.' without a following comma-decimal is not
        # treated as EU thousands (e.g. "29.999" stays invalid as an
        # over-precise fraction).
        numeric = (
            r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"   # 1,299.99
            r"|\d+(?:\.\d{1,2})?"                  # 29.99 / 1000
            r"|\d{1,3}(?:\.\d{3})+,\d{1,2}"       # 1.234,56
            r"|\d+(?:,\d{1,2})?"                   # 29,99
        )
        return bool(re.fullmatch(numeric, body))

    def validate_rating(self) -> bool:
        """Validate a rating (e.g. '4.5 out of 5'), tolerating real-world variants.

        Accepts: '4.5 out of 5', bare '4.5', '4.5/5', and prefixed forms
        like 'Rated 4.5' / 'Rating: 4.8'.
        """
        if not self.rating:
            return False

        rating = self.rating.strip()
        if not rating:
            return False

        number = r"(?:[0-4](?:\.[0-9])?|5(?:\.0)?)"
        # "4.5 out of 5"
        if re.fullmatch(rf"{number}\s+out\s+of\s+5", rating):
            return True
        # "4.5"
        if re.fullmatch(number, rating):
            return True
        # "4.5/5"
        if re.fullmatch(rf"{number}/5", rating):
            return True
        # "Rated 4.5" / "Rating : 4.8 / 5" (leading free text, trailing denom optional)
        return bool(re.fullmatch(rf"[A-Za-z]+\s*[:\-]?\s*{number}(?:\s*/\s*5)?", rating))
