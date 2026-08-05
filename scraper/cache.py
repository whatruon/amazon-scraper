from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_VERSION = "1"

# Leftover temp files (from interrupted atomic_write calls) older than this are
# swept on the next cache operation, so crashed writes never accumulate.
ORPHAN_TMP_MAX_AGE = 3600  # seconds

_TMP_PREFIX = ".tmp-"
_TMP_SUFFIX = ".tmp"

# Names of the files this cache manages: <64-hex sha256>.html / .meta.json.
_CACHE_KEY_RE = re.compile(r"^[0-9a-f]{64}\.html$")
_CACHE_META_RE = re.compile(r"^[0-9a-f]{64}\.meta\.json$")


@dataclass
class CacheEntry:
    url: str
    cached_at: float  # Unix timestamp
    ttl_seconds: int
    version: str = CACHE_VERSION


class CacheWriteError(OSError):
    """Internal error raised when an atomic file write cannot complete."""


class HtmlCache:
    """Disk-based cache for HTML responses, keyed by URL hash.

    Each cached URL stores two files under *cache_dir*:
        <key>.html      — the raw HTML content
        <key>.meta.json — JSON-serialized CacheEntry metadata

    Cache entries are invalidated by TTL.  A get() for an expired entry
    returns None and cleans up the stale files automatically.
    """

    def __init__(
        self,
        cache_dir: str | Path = "cache",
        ttl_seconds: int = 3600,
    ) -> None:
        self._dir = Path(cache_dir)
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str) -> str | None:
        """Return cached HTML for *url*, or None if not cached / expired."""
        key = self._key(url)
        # Cleanup orphaned temp files (including any for this entry) left by
        # interrupted atomic_write calls.
        self._cleanup_temps(key)
        html_path = self._html_path(key)
        meta_path = self._meta_path(key)

        if not html_path.exists():
            # Orphaned meta — clean up
            self._remove(key)
            self._misses += 1
            return None
        if not meta_path.exists():
            self._misses += 1
            return None

        entry = self._read_meta(meta_path)
        if entry is None:
            # Corrupted meta — clean up stale files
            self._remove(key)
            self._misses += 1
            return None

        if entry.version != CACHE_VERSION:
            self._remove(key)
            self._misses += 1
            return None

        if self._is_expired(entry):
            self._remove(key)
            if log.isEnabledFor(logging.DEBUG):
                log.debug("Cache expired for %s", url)
            self._misses += 1
            return None

        html = self._read_html(html_path)
        if html is None:
            self._remove(key)
            self._misses += 1
            return None

        self._hits += 1
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Cache hit for %s (%d bytes)", url, len(html))
        return html

    def put(self, url: str, html: str) -> None:
        """Store *html* for *url* in the cache."""
        self._dir.mkdir(parents=True, exist_ok=True)
        key = self._key(url)
        entry = CacheEntry(
            url=url,
            cached_at=time.time(),
            ttl_seconds=self._ttl,
        )

        # Write meta first so a crash after writing HTML but before meta
        # is detectable (meta missing → entry treated as absent).
        atomic_write(self._meta_path(key), json.dumps(asdict(entry)))
        atomic_write(self._html_path(key), html)

        if log.isEnabledFor(logging.DEBUG):
            log.debug("Cached %s (%d bytes)", url, len(html))

    def invalidate(self, url: str) -> None:
        """Remove the cache entry for *url*, if one exists."""
        self._remove(self._key(url))

    def clear(self) -> None:
        """Remove all cache entries managed by this cache."""
        if not self._dir.exists():
            return
        for path in list(self._dir.iterdir()):
            name = path.name
            if (
                _CACHE_KEY_RE.fullmatch(name)
                or _CACHE_META_RE.fullmatch(name)
                or name.startswith(_TMP_PREFIX)
            ):
                path.unlink(missing_ok=True)

    def stats(self) -> dict:
        """Return summary statistics about the cache."""
        total = 0
        total_bytes = 0
        expired = 0
        if self._dir.exists():
            for path in self._dir.iterdir():
                if path.suffix != ".html":
                    continue
                try:
                    total_bytes += path.stat().st_size
                except OSError:
                    # File vanished between listing and stat — skip it.
                    continue
                total += 1
                meta_path = self._meta_path(path.stem)
                entry = self._read_meta(meta_path)
                if entry and self._is_expired(entry):
                    expired += 1

        return {
            "total_entries": total,
            "total_bytes": total_bytes,
            "expired_entries": expired,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses)
            if (self._hits + self._misses) > 0
            else 0.0,
            "cache_dir": str(self._dir),
            "ttl_seconds": self._ttl,
        }

    def cached_at(self, url: str) -> float | None:
        """Return the cached_at timestamp stored for *url*, or None.

        Returns None when the entry is absent, corrupted, or its meta file
        cannot be read. Only the meta file is consulted — the HTML is never
        read here.
        """
        entry = self._read_meta(self._meta_path(self._key(url)))
        return entry.cached_at if entry else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _html_path(self, key: str) -> Path:
        return self._dir / f"{key}.html"

    def _meta_path(self, key: str) -> Path:
        return self._dir / f"{key}.meta.json"

    def _is_expired(self, entry: CacheEntry) -> bool:
        return (time.time() - entry.cached_at) > entry.ttl_seconds

    def _remove(self, key: str) -> None:
        self._html_path(key).unlink(missing_ok=True)
        self._meta_path(key).unlink(missing_ok=True)
        self._cleanup_temps(key)

    def _cleanup_temps(self, key: str | None = None) -> None:
        """Remove orphaned temp files left by interrupted atomic_write calls.

        Temp files for *key* (identifiable because their name embeds the target
        filename) are removed unconditionally. Any other leftover ``*.tmp`` file
        older than ORPHAN_TMP_MAX_AGE is swept as a safety net, so a crashed
        write for an entry that is never touched again still gets cleaned up.
        Fresh foreign temps are preserved so a concurrent in-progress write is
        never disturbed.
        """
        if not self._dir.exists():
            return
        cutoff = time.time() - ORPHAN_TMP_MAX_AGE
        marker = f".{key}." if key else None
        for p in self._dir.glob(f"*{_TMP_SUFFIX}"):
            with contextlib.suppress(OSError):
                is_target = marker is not None and marker in p.name
                if is_target or p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)

    @staticmethod
    def _read_meta(path: Path) -> CacheEntry | None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return CacheEntry(**data)
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            return None

    @staticmethod
    def _read_html(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None


def _write_all(fd: int, data: bytes, tmp: str) -> None:
    """Write *data* to *fd* in full, fsyncing, and raise on a short write."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            msg = f"short write while writing to {tmp}"
            raise CacheWriteError(msg)
        view = view[written:]
    os.fsync(fd)


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of *directory* so a completed rename is durable."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        # Directories cannot be opened as files on some platforms.
        return
    with contextlib.suppress(OSError):
        os.fsync(fd)
    os.close(fd)


def atomic_write(path: Path, content: str) -> None:
    """Atomically write *content* to *path* via tempfile + rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The target filename is embedded in the temp name so cache cleanup can
    # find leftovers; the prefix stays short for platform portability.
    fd, tmp = tempfile.mkstemp(
        prefix=_TMP_PREFIX,
        suffix=f".{path.name}{_TMP_SUFFIX}",
        dir=path.parent,
    )
    try:
        _write_all(fd, content.encode("utf-8"), tmp)
    except Exception:
        # Never leave the temp file behind when writing/fsync failed.
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    finally:
        os.close(fd)
    try:
        # os.replace is atomic on the same filesystem and works on Windows too.
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    # Make the rename itself durable once the file is in place.
    _fsync_dir(path.parent)
