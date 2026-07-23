from __future__ import annotations


class ScrapeError(Exception):
    """Base exception for all scraper errors."""

    def __init__(self, url: str, reason: str, stage: str = "scrape"):
        self.url = url
        self.reason = reason
        self.stage = stage
        super().__init__(f"[{stage}] {reason}: {url}")


class NavigationError(ScrapeError):
    """Navigation failed (timeout, connection error, etc.)."""

    def __init__(self, url: str, reason: str, stage: str = "navigation"):
        super().__init__(url, reason, stage)


class ParseError(ScrapeError):
    """HTML parsing or data extraction failed."""

    def __init__(self, url: str, reason: str, stage: str = "parse"):
        super().__init__(url, reason, stage)


class CaptchaError(ScrapeError):
    """CAPTCHA challenge detected and could not be bypassed."""

    def __init__(self, url: str, reason: str = "CAPTCHA detected", stage: str = "captcha"):
        super().__init__(url, reason, stage)


class BlockedError(ScrapeError):
    """Request blocked by Amazon (HTTP 503, rate limit, etc.)."""

    def __init__(self, url: str, reason: str = "Request blocked", stage: str = "blocked"):
        super().__init__(url, reason, stage)


class TimeoutError(ScrapeError):
    """Operation exceeded its time limit."""

    def __init__(self, url: str, reason: str = "Operation timed out", stage: str = "timeout"):
        super().__init__(url, reason, stage)
