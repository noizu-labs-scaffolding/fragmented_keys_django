"""Adapter between Django cache and fragmented_keys CacheHandler protocol."""

from __future__ import annotations

import json
import pickle
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.core.cache.backends.base import BaseCache


class DjangoCacheHandler:
    """Adapter between Django cache and fragmented_keys CacheHandler protocol.

    This class wraps any Django cache backend and implements the
    fragmented_keys.protocols.CacheHandler protocol, allowing
    fragmented_keys to work with any Django-compatible cache backend
    (Redis, Memcached, database, etc.).
    """

    def __init__(self, cache_name: str = "default") -> None:
        """Initialize the handler with a Django cache backend.

        Args:
            cache_name: Name of the Django cache to use (default: "default")
        """
        from django.core.cache import caches

        self._cache = caches[cache_name]
        self._cache_name = cache_name

    def group_name(self) -> str:
        """Return a unique identifier for this handler type."""
        cache_class_name = self._cache.__class__.__name__
        return f"DjangoCacheHandler:{cache_class_name}:{self._cache_name}"

    def get(self, key: str) -> str | None:
        """Fetch a single value by key. Returns None on miss.

        Args:
            key: Cache key to fetch

        Returns:
            String value or None if not found
        """
        val = self._cache.get(key)
        if val is None:
            return None

        # Convert various Django cache types to string for fragmented_keys
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            return val.decode("utf-8")
        elif isinstance(val, (dict, list)):
            return json.dumps(val)
        elif isinstance(val, (int, float, bool)):
            return str(val)
        else:
            # For complex objects, try to return their string representation
            # Or if they were pickled by Django cache
            try:
                return str(val)
            except Exception:
                return None

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Store a value, optionally with a TTL in seconds.

        Args:
            key: Cache key to store under
            value: String value to store
            ttl: Time-to-live in seconds (None for no expiration)
        """
        self._cache.set(key, value, timeout=ttl)

    def get_multi(self, keys: list[str]) -> dict[str, str]:
        """Fetch multiple values at once.

        Returns dict of found key-value pairs. Keys not found
        are omitted from the result.

        Args:
            keys: List of cache keys to fetch

        Returns:
            Dictionary mapping keys that were found to their values
        """
        results = {}
        items = self._cache.get_many(keys)

        for key, val in items.items():
            # Convert to string, same logic as get()
            if val is None:
                continue
            if isinstance(val, str):
                results[key] = val
            elif isinstance(val, bytes):
                results[key] = val.decode("utf-8")
            elif isinstance(val, (dict, list)):
                results[key] = json.dumps(val)
            else:
                results[key] = str(val)

        return results