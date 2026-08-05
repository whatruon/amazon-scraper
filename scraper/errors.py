from __future__ import annotations


class ScrapeError(Exception):
    """Base exception for all scraper errors.

    Each subclass declares its phase via the class-level ``stage`` attribute and
    supplies a specific default reason via ``default_reason``. The stage is a
    property of the error *type*, not of a single raise site, so caught errors
    always report their designated phase consistently.
    """

    stage = "scrape"
    default_reason = "Scraping failed"

    def __init__(
        self,
        url: str,
        reason: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.url = url
        self.reason = reason if reason is not None else self.default_reason
        self.hint = hint
        message = f"[{self.stage}] {self.reason}: {url}"
        if hint:
            message = f"{message}\nHINT: {hint}"
        super().__init__(message)


class NavigationError(ScrapeError):
    """Navigation failed before the page content could be loaded."""

    stage = "navigation"
    default_reason = "Failed to navigate to the requested page"


class ParseError(ScrapeError):
    """Navigation succeeded, but HTML parsing or data extraction failed."""

    stage = "parse"
    default_reason = "Failed to parse content from the page HTML"


class NavigationTimeout(NavigationError):
    """The page did not (fully) load within the allotted time."""

    stage = "timeout"
    default_reason = (
        "Page load exceeded the time limit; the browser waited too long for "
        "the DOM to reach a stable state"
    )


class CaptchaError(NavigationError):
    """Amazon served a CAPTCHA challenge that could not be solved automatically."""

    stage = "captcha"
    default_reason = (
        "CAPTCHA challenge presented and could not be bypassed; the page "
        "refused to load for an automated client"
    )
    default_hint = (
        "Wait longer between requests, rotate the user agent, or use a "
        "residential proxy so the request is not flagged as bot traffic"
    )

    def __init__(self, url: str, reason: str | None = None, hint: str | None = None) -> None:
        super().__init__(url, reason, hint if hint is not None else self.default_hint)


class BlockedError(NavigationError):
    """Request was refused by Amazon (HTTP 503 / 509, bot rate limit, redirect trap)."""

    stage = "blocked"
    default_reason = (
        "Amazon blocked the request (HTTP 503/509 or bot-detection); no "
        "product data could be retrieved"
    )
    default_hint = (
        "Reduce request frequency, space out retries with backoff, or rotate "
        "the IP/proxy; the account or session may also be rate-limited"
    )

    def __init__(self, url: str, reason: str | None = None, hint: str | None = None) -> None:
        super().__init__(url, reason, hint if hint is not None else self.default_hint)
