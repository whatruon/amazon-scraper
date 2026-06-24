from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime, timezone
from typing import Optional


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
    schema_version: str = "1.0"
    scraped_at: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self, indent: int = 2) -> str:
        data = self.to_dict()
        data["schema_version"] = self.schema_version
        data["scraped_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def validate_asin(self) -> bool:
        """Validate ASIN format (10 alphanumeric characters, uppercase)."""
        if not self.asin:
            return False
        return bool(re.match(r"^[A-Z0-9]{10}$", self.asin))

    def validate_price(self) -> bool:
        """Validate price format (currency symbol followed by number with optional commas and decimal places)."""
        if not self.price:
            return False
        # Currency symbol, then digits (with comma thousands separators), optional decimals
        # Allows: $29, $29.99, $1000, $1,299.99, $1,000,000.99
        return bool(re.match(r"^[^\d\s](?:\d{1,3}|\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d{1,2})?$", self.price))

    def validate_rating(self) -> bool:
        """Validate rating format (number out of 5, e.g., '4.5 out of 5')."""
        if not self.rating:
            return False
        # Rating must be 0-5 with up to one decimal place (Amazon format)
        return bool(re.match(r"^(?:[0-4](?:\.[0-9])?|5(?:\.0)?)\s+out\s+of\s+5$", self.rating))


class ScrapeError(Exception):
    def __init__(self, url: str, reason: str, stage: str = "scrape"):
        self.url = url
        self.reason = reason
        self.stage = stage
        super().__init__(f"[{stage}] {reason}: {url}")
