"""Tests for YAML config loading."""
from __future__ import annotations

from scraper.config import CONFIG_KEYS, load_config


def test_load_config_missing_file(tmp_path):
    assert load_config(str(tmp_path / "nope.yaml")) == {}


def test_load_config_valid(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("retries: 3\ntimeout: 20000\nzip: \"10001\"\nverbose: true\n", encoding="utf-8")
    cfg = load_config(str(cfg_path))
    assert cfg["retries"] == 3
    assert cfg["timeout"] == 20000
    assert cfg["zip"] == "10001"
    assert cfg["verbose"] is True


def test_load_config_invalid_yaml(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("retries: [unclosed\n", encoding="utf-8")
    assert load_config(str(cfg_path)) == {}


def test_load_config_non_mapping(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert load_config(str(cfg_path)) == {}


def test_config_keys_match_cli_dest_names():
    assert "retries" in CONFIG_KEYS
    assert "headed" in CONFIG_KEYS
    assert "zip" in CONFIG_KEYS
    assert "cache_ttl" in CONFIG_KEYS
