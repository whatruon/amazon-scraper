from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime, timezone
from typing import Optional


@dataclasses.dataclass
class SearchResult:
    """Structured data from a search-results page card."""

    url: str
    asin: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    is_prime: bool = False


@dataclasses.dataclass
class Variant:
    """Product variant (color, size, style, etc.)."""

    asin: str
    label: Optional[str] = None
    price: Optional[str] = None
    is_selected: bool = False


@dataclasses.dataclass
class Product:
    title: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    images: list[str] = dataclasses.field(default_factory=list)
    bullets: list[str] = dataclasses.field(default_factory=list)
    availability: Optional[str] = None
    asin: Optional[str] = None
    brand: Optional[str] = None

    # Product details
    model_number: Optional[str] = None
    date_first_available: Optional[str] = None
    manufacturer: Optional[str] = None
    item_weight: Optional[str] = None
    dimensions: Optional[str] = None
    department: Optional[str] = None
    best_sellers_rank: Optional[str] = None

    # Categorization
    category_path: Optional[str] = None

    # Variants
    variants: list[Variant] = dataclasses.field(default_factory=list)

    # Metadata
    schema_version: str = "1.0"
    scraped_at: Optional[str] = None

    # Tracks how each field was extracted (e.g. "css: #productTitle", "url_regex", None)
    extraction_quality: dict = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dataclasses.asdict(self)
        return data

    def to_json(self, indent: int = 2) -> str:
        data = self.to_dict()
        if data["scraped_at"] is None:
            data["scraped_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def validate_asin(self) -> bool:
        """Validate ASIN format (10 alphanumeric characters, uppercase)."""
        if not self.asin:
            return False
        return bool(re.match(r"^[A-Z0-9]{10}$", self.asin))

    def validate_price(self) -> bool:
        """Validate price format (currency symbol followed by number with optional commas and decimal places).

        Supports: $ £ € ¥ ₹. Amazon in other locales (e.g., R$ Brazil, MX$ Mexico) will fail validation.
        """
        if not self.price:
            return False
        return bool(re.match(r"^[$£€¥₹](?:\d{1,3}|\d{1,3}(?:,\d{3})+|\d{4})(?:\.\d{1,2})?$", self.price))

    def validate_rating(self) -> bool:
        """Validate rating format (number out of 5, e.g., '4.5 out of 5')."""
        if not self.rating:
            return False
        return bool(re.match(r"^(?:[0-4](?:\.[0-9])?|5(?:\.0)?)\s+out\s+of\s+5$", self.rating))


class ScrapeError(Exception):
    def __init__(self, url: str, reason: str, stage: str = "scrape"):
        self.url = url
        self.reason = reason
        self.stage = stage
        super().__init__(f"[{stage}] {reason}: {url}")
