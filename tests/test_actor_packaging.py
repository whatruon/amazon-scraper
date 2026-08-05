# noqa: INP001 - tests are an implicit namespace package by design
"""Checks for the Apify packaging files that ship with the repo."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    with open(ROOT / relative, encoding="utf-8") as f:
        return json.load(f)


def test_actor_json_valid_and_complete():
    data = _load(".actor/actor.json")
    assert data["actorSpecification"] == 1
    assert data["name"] == "amazon-scraper"
    assert data["dockerfile"] == "../Dockerfile"
    assert data["input"] == "./INPUT_SCHEMA.json"


def test_input_schema_is_valid_object():
    schema = _load(".actor/INPUT_SCHEMA.json")
    assert schema["type"] == "object"
    assert schema["schemaVersion"] == 1
    props = schema["properties"]
    assert "searchTerm" in props
    assert "productUrls" in props
    assert "domain" in props
    assert "proxy" in props
    assert props["proxy"]["editor"] == "proxy"


def test_input_schema_properties_have_types():
    schema = _load(".actor/INPUT_SCHEMA.json")
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"{name} missing type"


def test_search_term_and_product_urls_are_nullable():
    schema = _load(".actor/INPUT_SCHEMA.json")
    assert schema["properties"]["searchTerm"]["nullable"] is True
    assert schema["properties"]["productUrls"]["nullable"] is True


def test_dockerfile_references_known_files():
    dockerfile = ROOT / "Dockerfile"
    assert dockerfile.exists()
    text = dockerfile.read_text(encoding="utf-8")
    assert "apify/actor-python-playwright" in text  # expected base image
    assert "python -m src" in text or '"python", "-m", "src"' in text  # the CMD entry point
    assert (ROOT / "src/__main__.py").exists()


def test_requirements_pins_apify_sdk():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "apify" in reqs
    assert "playwright" in reqs
