"""
telegram_bot/cache.py
=====================
Thread-safe in-memory TTL cache.
Shared across all handlers to avoid redundant API calls (5-min default TTL).
"""
import time
import threading
from typing import Any


class TTLCache:
    """Simple thread-safe key/value cache with per-entry expiry."""

    def __init__(self, default_ttl: int = 300):
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Return cached value if not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value; expires after ttl seconds (default: self._default_ttl)."""
        expires_at = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        with self._lock:
            self._store[key] = (value, expires_at)

    def invalidate(self, prefix: str = "") -> int:
        """Remove all keys that start with prefix (empty = clear all). Returns count."""
        with self._lock:
            if not prefix:
                count = len(self._store)
                self._store.clear()
                return count
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "total_keys": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self._hits / total:.0%}" if total else "n/a",
            }
