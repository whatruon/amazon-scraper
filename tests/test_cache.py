"""Tests for the HtmlCache disk-based caching layer."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scraper.cache import HtmlCache, CacheEntry


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path: Path) -> HtmlCache:
    return HtmlCache(cache_dir=tmp_path / "cache", ttl_seconds=300)


@pytest.fixture
def small_ttl_cache(tmp_path: Path) -> HtmlCache:
    return HtmlCache(cache_dir=tmp_path / "cache_small", ttl_seconds=1)


# ------------------------------------------------------------------
# Basic put / get
# ------------------------------------------------------------------

class TestPutGet:

    def test_put_and_get(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        result = cache.get("https://amazon.com/dp/B0TEST")
        assert result == "<html>test</html>"

    def test_get_uncached_url(self, cache: HtmlCache):
        result = cache.get("https://amazon.com/dp/B0MISSING")
        assert result is None

    def test_put_overwrites_existing(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0TEST", "<html>v1</html>")
        cache.put("https://amazon.com/dp/B0TEST", "<html>v2</html>")
        result = cache.get("https://amazon.com/dp/B0TEST")
        assert result == "<html>v2</html>"

    def test_different_urls(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.put("https://amazon.com/dp/B", "<html>B</html>")
        assert cache.get("https://amazon.com/dp/A") == "<html>A</html>"
        assert cache.get("https://amazon.com/dp/B") == "<html>B</html>"

    def test_empty_html(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/EMPTY", "")
        assert cache.get("https://amazon.com/dp/EMPTY") == ""

    def test_special_chars_in_url(self, cache: HtmlCache):
        url = "https://amazon.com/s?k=noise+canceling+headphones&ref=sr_1_1&c=日本語"
        cache.put(url, "<html>special</html>")
        assert cache.get(url) == "<html>special</html>"


# ------------------------------------------------------------------
# TTL expiration
# ------------------------------------------------------------------

class TestTTL:

    def test_expired_entry_returns_none(self, small_ttl_cache: HtmlCache):
        small_ttl_cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        time.sleep(1.1)
        result = small_ttl_cache.get("https://amazon.com/dp/B0TEST")
        assert result is None

    def test_fresh_entry_within_ttl(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        # Should still be fresh (300s TTL)
        result = cache.get("https://amazon.com/dp/B0TEST")
        assert result == "<html>test</html>"

    def test_expired_entry_removes_files(self, small_ttl_cache: HtmlCache):
        small_ttl_cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        key = small_ttl_cache._key("https://amazon.com/dp/B0TEST")
        html_path = small_ttl_cache._html_path(key)
        meta_path = small_ttl_cache._meta_path(key)
        assert html_path.exists()
        assert meta_path.exists()

        time.sleep(1.1)
        small_ttl_cache.get("https://amazon.com/dp/B0TEST")

        assert not html_path.exists()
        assert not meta_path.exists()

    def test_custom_ttl_per_instance(self, tmp_path: Path):
        long_cache = HtmlCache(cache_dir=tmp_path / "long", ttl_seconds=9999)
        long_cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        # Set system clock forward is unreliable, but we can verify
        # the TTL was stored by reading the meta file
        key = long_cache._key("https://amazon.com/dp/B0TEST")
        meta_path = long_cache._meta_path(key)
        meta = json.loads(meta_path.read_text())
        assert meta["ttl_seconds"] == 9999


# ------------------------------------------------------------------
# invalidation
# ------------------------------------------------------------------

class TestInvalidate:

    def test_invalidate_existing(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        cache.invalidate("https://amazon.com/dp/B0TEST")
        assert cache.get("https://amazon.com/dp/B0TEST") is None

    def test_invalidate_nonexistent(self, cache: HtmlCache):
        cache.invalidate("https://amazon.com/dp/B0MISSING")
        # Should not raise

    def test_invalidate_does_not_affect_others(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.put("https://amazon.com/dp/B", "<html>B</html>")
        cache.invalidate("https://amazon.com/dp/A")
        assert cache.get("https://amazon.com/dp/A") is None
        assert cache.get("https://amazon.com/dp/B") == "<html>B</html>"

    def test_invalidate_removes_files(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        key = cache._key("https://amazon.com/dp/B0TEST")
        html_path = cache._html_path(key)
        meta_path = cache._meta_path(key)
        assert html_path.exists()
        assert meta_path.exists()

        cache.invalidate("https://amazon.com/dp/B0TEST")

        assert not html_path.exists()
        assert not meta_path.exists()


# ------------------------------------------------------------------
# clear
# ------------------------------------------------------------------

class TestClear:

    def test_clears_all_entries(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.put("https://amazon.com/dp/B", "<html>B</html>")
        cache.clear()
        assert cache.get("https://amazon.com/dp/A") is None
        assert cache.get("https://amazon.com/dp/B") is None

    def test_clear_empty_cache(self, cache: HtmlCache):
        cache.clear()  # should not raise

    def test_clear_removes_directory_content(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.clear()
        assert list(cache._dir.iterdir()) == []

    def test_clear_leaves_other_files(self, cache: HtmlCache):
        # Create a non-cache file in the directory
        cache._dir.mkdir(parents=True, exist_ok=True)
        (cache._dir / "README.txt").write_text("keep me")
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.clear()
        # Cache files are gone
        assert cache.get("https://amazon.com/dp/A") is None
        # Non-cache file should remain
        assert (cache._dir / "README.txt").exists()


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

class TestStats:

    def test_stats_empty(self, cache: HtmlCache):
        stats = cache.stats()
        assert stats["total_entries"] == 0
        assert stats["total_bytes"] == 0
        assert stats["expired_entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["cache_dir"] == str(cache._dir)
        assert stats["ttl_seconds"] == 300

    def test_stats_tracks_hits_and_misses(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.get("https://amazon.com/dp/A")  # hit
        cache.get("https://amazon.com/dp/B")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_stats_entry_count(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.put("https://amazon.com/dp/B", "<html>BB</html>")
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["total_bytes"] > 0

    def test_stats_after_clear(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.clear()
        stats = cache.stats()
        assert stats["total_entries"] == 0

    def test_stats_hit_rate_no_accesses(self, cache: HtmlCache):
        stats = cache.stats()
        assert stats["hit_rate"] == 0.0

    def test_stats_all_hits(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/A", "<html>A</html>")
        cache.get("https://amazon.com/dp/A")
        cache.get("https://amazon.com/dp/A")
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0


# ------------------------------------------------------------------
# Corruption & edge cases
# ------------------------------------------------------------------

class TestCorruption:

    def test_corrupted_meta_returns_none(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        # Corrupt the meta file
        cache._meta_path(key).write_text("not json", encoding="utf-8")
        assert cache.get("https://amazon.com/dp/B0OK") is None

    def test_corrupted_meta_cleans_up(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        cache._meta_path(key).write_text("not json", encoding="utf-8")
        cache.get("https://amazon.com/dp/B0OK")
        # Files should be cleaned up
        assert not cache._html_path(key).exists()
        assert not cache._meta_path(key).exists()

    def test_missing_meta_returns_none(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        cache._meta_path(key).unlink()
        assert cache.get("https://amazon.com/dp/B0OK") is None

    def test_missing_html_returns_none(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        cache._html_path(key).unlink()
        assert cache.get("https://amazon.com/dp/B0OK") is None

    def test_missing_html_cleans_up_meta(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        cache._html_path(key).unlink()
        cache.get("https://amazon.com/dp/B0OK")
        assert not cache._meta_path(key).exists()

    def test_missing_meta_dir_returns_none(self, cache: HtmlCache):
        result = cache.get("https://amazon.com/dp/B0TEST")
        assert result is None

    def test_truncated_html(self, cache: HtmlCache):
        cache.put("https://amazon.com/dp/B0OK", "<html>ok</html>")
        key = cache._key("https://amazon.com/dp/B0OK")
        # truncate
        cache._html_path(key).write_text("", encoding="utf-8")
        assert cache.get("https://amazon.com/dp/B0OK") == ""


def test_cache_version_mismatch(tmp_path: Path):
    """Entries with a different CACHE_VERSION are treated as absent."""
    c = HtmlCache(cache_dir=tmp_path / "ver", ttl_seconds=300)
    c.put("https://amazon.com/dp/B0TEST", "<html>old</html>")
    key = c._key("https://amazon.com/dp/B0TEST")
    meta_path = c._meta_path(key)
    meta = json.loads(meta_path.read_text())
    meta["version"] = "0"
    meta_path.write_text(json.dumps(meta))

    result = c.get("https://amazon.com/dp/B0TEST")
    assert result is None

    # Stale files are cleaned up
    assert not c._html_path(key).exists()
    assert not c._meta_path(key).exists()


# ------------------------------------------------------------------
# Re-initialization (persistence across instances)
# ------------------------------------------------------------------

class TestPersistence:

    def test_reinit_reuses_cache(self, tmp_path: Path):
        d = tmp_path / "persist"
        c1 = HtmlCache(cache_dir=d, ttl_seconds=300)
        c1.put("https://amazon.com/dp/B0TEST", "<html>persisted</html>")

        c2 = HtmlCache(cache_dir=d, ttl_seconds=300)
        result = c2.get("https://amazon.com/dp/B0TEST")
        assert result == "<html>persisted</html>"

    def test_reinit_tracks_stats_independently(self, tmp_path: Path):
        d = tmp_path / "stats"
        c1 = HtmlCache(cache_dir=d, ttl_seconds=300)
        c1.put("https://amazon.com/dp/B0TEST", "<html>test</html>")
        c1.get("https://amazon.com/dp/B0TEST")  # hit on c1

        c2 = HtmlCache(cache_dir=d, ttl_seconds=300)
        # c2 has its own hit counter, but can read the cached data
        assert c2.get("https://amazon.com/dp/B0TEST") == "<html>test</html>"
        assert c2.stats()["hits"] == 1
        assert c2.stats()["misses"] == 0


# ------------------------------------------------------------------
# Key derivation
# ------------------------------------------------------------------

class TestKeyDerivation:

    def test_key_is_deterministic(self):
        url = "https://amazon.com/dp/B0TEST"
        assert HtmlCache._key(url) == HtmlCache._key(url)

    def test_key_differs_for_different_urls(self):
        assert HtmlCache._key("https://amazon.com/dp/A") != HtmlCache._key("https://amazon.com/dp/B")

    def test_key_is_hex_string(self):
        key = HtmlCache._key("https://amazon.com/dp/B0TEST")
        assert len(key) == 64
        int(key, 16)  # should not raise


# ------------------------------------------------------------------
# Constructor defaults
# ------------------------------------------------------------------

class TestConstructor:

    def test_default_cache_dir_is_cache(self):
        c = HtmlCache()
        assert str(c._dir) == "cache"

    def test_default_ttl_is_3600(self):
        c = HtmlCache()
        assert c._ttl == 3600

    def test_custom_cache_dir(self, tmp_path: Path):
        c = HtmlCache(cache_dir=tmp_path / "mycache")
        assert str(c._dir) == str(tmp_path / "mycache")

    def test_custom_ttl(self):
        c = HtmlCache(ttl_seconds=7200)
        assert c._ttl == 7200


# ------------------------------------------------------------------
# Large content
# ------------------------------------------------------------------

def test_large_html_content(cache: HtmlCache):
    """Verify caching works with large HTML (>100KB)."""
    large = "<html>" + "x" * 200_000 + "</html>"
    cache.put("https://amazon.com/dp/LARGE", large)
    result = cache.get("https://amazon.com/dp/LARGE")
    assert result == large
    assert len(result) == len(large)


def test_put_and_get_unicode(cache: HtmlCache):
    """Verify Unicode content is preserved."""
    html = "<html>¥€£ préservé 日本語</html>"
    cache.put("https://amazon.co.jp/dp/B0TEST", html)
    result = cache.get("https://amazon.co.jp/dp/B0TEST")
    assert result == html


# ------------------------------------------------------------------
# CacheEntry dataclass
# ------------------------------------------------------------------

class TestCacheEntry:

    def test_entry_defaults(self):
        entry = CacheEntry(url="https://amazon.com/dp/B0TEST", cached_at=1000.0, ttl_seconds=300)
        assert entry.version == "1"
        assert entry.url == "https://amazon.com/dp/B0TEST"
        assert entry.cached_at == 1000.0
        assert entry.ttl_seconds == 300

    def test_entry_serialization_roundtrip(self):
        entry = CacheEntry(url="https://amazon.com/dp/B0TEST", cached_at=1000.0, ttl_seconds=300)
        data = json.loads(json.dumps({
            "url": entry.url,
            "cached_at": entry.cached_at,
            "ttl_seconds": entry.ttl_seconds,
            "version": entry.version,
        }))
        restored = CacheEntry(**data)
        assert restored.url == entry.url
        assert restored.cached_at == entry.cached_at
        assert restored.ttl_seconds == entry.ttl_seconds
        assert restored.version == entry.version
