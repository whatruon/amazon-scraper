
"""Tests for the CLI entry point (search mode)."""
from __future__ import annotations

import json
import signal
import sys
from unittest.mock import MagicMock

import pytest

import cli
import scraper.orchestrator as orchestrator_mod
from scraper.models import Product, SearchResult

_PRODUCT_HTML = (
    "<html><body>"
    "<span id='productTitle'>P</span>"
    "<span id='priceblock_ourprice'>$29.99</span>"
    "</body></html>"
)


def test_cli_search_mode_scrapes_result_urls(monkeypatch, tmp_path):
    """Search mode must navigate to each SearchResult's .url, not the object itself."""
    session = MagicMock()
    page = MagicMock()
    page.content.return_value = _PRODUCT_HTML
    session.navigate_with_retry.return_value = page

    monkeypatch.setattr(cli, "BrowserSession", lambda **kwargs: session)
    monkeypatch.setattr(orchestrator_mod, "search_amazon_func", lambda *args, **kwargs: [
        SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
    ])

    out_path = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["cli", "-s", "test query", "-o", str(out_path), "-n", "1"])

    cli.main()

    assert session.navigate_with_retry.call_args[0][0] == "https://www.amazon.com/dp/B0TESTABC1"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["asin"] == "B0TESTABC1"
    assert data[0]["price"] == "$29.99"
    assert data[0]["scraped_at"] is not None


def test_cli_search_mode_empty_on_failed_navigation(monkeypatch, tmp_path):
    """A failed navigation must not crash the CLI; results are simply skipped."""
    session = MagicMock()
    session.navigate_with_retry.side_effect = cli.ScrapeError("https://x", reason="boom")

    monkeypatch.setattr(cli, "BrowserSession", lambda **kwargs: session)
    monkeypatch.setattr(orchestrator_mod, "search_amazon_func", lambda *args, **kwargs: [
        SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
    ])

    out_path = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["cli", "-s", "test query", "-o", str(out_path), "-n", "1"])

    cli.main()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data == []


def test_cli_config_zip_int_is_coerced_to_str(monkeypatch, tmp_path):
    """An unquoted int zip in config.yaml must reach set_zip_code as a string."""
    session = MagicMock()
    page = MagicMock()
    page.content.return_value = _PRODUCT_HTML
    session.navigate_with_retry.return_value = page

    monkeypatch.setattr(cli, "BrowserSession", lambda **kwargs: session)
    monkeypatch.setattr(orchestrator_mod, "search_amazon_func", lambda *args, **kwargs: [
        SearchResult(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
    ])

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("zip: 10035\nretries: 1\n", encoding="utf-8")
    out_path = tmp_path / "results.json"

    monkeypatch.setattr(sys, "argv", [
        "cli", "-s", "test query", "-o", str(out_path), "-n", "1",
        "--config", str(cfg_path),
    ])

    cli.main()

    assert session.set_zip_code.call_args.kwargs["zip_code"] == "10035"


def test_get_amazon_domain_strips_port():
    """A port in the URL must not leak into the resolved domain."""
    assert cli._get_amazon_domain("https://www.amazon.com:8080/dp/B0XXX") == "amazon.com"


def test_get_amazon_domain_smile_domain():
    """The smile. subdomain must be stripped before the domain lookup."""
    assert cli._get_amazon_domain("https://smile.amazon.co.uk/dp/X") == "amazon.co.uk"


def test_get_amazon_domain_non_amazon_defaults():
    """Non-Amazon hosts must fall back to the default domain."""
    assert cli._get_amazon_domain("https://example.com/x") == "amazon.com"


def test_get_amazon_domain_malformed_defaults():
    """Malformed/empty URLs must not crash and must fall back to amazon.com."""
    assert cli._get_amazon_domain("") == "amazon.com"
    assert cli._get_amazon_domain("not a url") == "amazon.com"


def test_handle_interrupt_sets_flag_then_exits():
    """The first interrupt sets the flag; the second one forces exit."""
    cli._interrupted = False
    try:
        cli._handle_interrupt(signal.SIGINT, None)
        assert cli._interrupted is True
        with pytest.raises(SystemExit) as exc_info:
            cli._handle_interrupt(signal.SIGINT, None)
        assert exc_info.value.code == 1
    finally:
        cli._interrupted = False


def test_cli_no_cache_flag_disables_config_cache(monkeypatch, tmp_path):
    """--no-cache must override cache: true from the config file."""
    session = MagicMock()
    monkeypatch.setattr(cli, "BrowserSession", lambda **kwargs: session)

    captured = {}
    def fake_orchestrator(**kwargs):
        captured.update(kwargs)
        orch = MagicMock()
        orch.scrape_search.return_value = [
            Product(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
        ]
        return orch
    monkeypatch.setattr(cli, "ScrapeOrchestrator", fake_orchestrator)

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("cache: true\n", encoding="utf-8")
    out_path = tmp_path / "results.json"

    monkeypatch.setattr(sys, "argv", [
        "cli", "-s", "test query", "-o", str(out_path), "-n", "1",
        "--config", str(cfg_path), "--no-cache",
    ])

    cli.main()

    assert captured["cache"] is None
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data[0]["asin"] == "B0TESTABC1"


def test_cli_config_cache_creates_html_cache(monkeypatch, tmp_path):
    """cache: true in config (without --no-cache) must construct HtmlCache."""
    session = MagicMock()
    monkeypatch.setattr(cli, "BrowserSession", lambda **kwargs: session)

    captured = {}
    def fake_orchestrator(**kwargs):
        captured.update(kwargs)
        orch = MagicMock()
        orch.scrape_search.return_value = [
            Product(url="https://www.amazon.com/dp/B0TESTABC1", asin="B0TESTABC1"),
        ]
        return orch
    monkeypatch.setattr(cli, "ScrapeOrchestrator", fake_orchestrator)

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("cache: true\n", encoding="utf-8")
    out_path = tmp_path / "results.json"

    monkeypatch.setattr(sys, "argv", [
        "cli", "-s", "test query", "-o", str(out_path), "-n", "1",
        "--config", str(cfg_path),
    ])

    cli.main()

    assert captured["cache"] is not None
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data[0]["asin"] == "B0TESTABC1"
