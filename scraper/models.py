from __future__ import annotations

import dataclasses
import json
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

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class ScrapeError(Exception):
    def __init__(self, url: str, reason: str, stage: str = "scrape"):
        self.url = url
        self.reason = reason
        self.stage = stage
        super().__init__(f"[{stage}] {reason}: {url}")
