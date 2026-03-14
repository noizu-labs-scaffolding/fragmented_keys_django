"""Adapter between Django cache and fragmented_keys CacheHandler protocol.

The ``fragmented_keys`` library needs a cache handler that speaks its
string-based protocol (:meth:`get` returns ``str | None``, :meth:`set`
accepts ``str``).  Django's cache API returns arbitrary Python objects
(dicts, lists, pickled models, etc.).

:class:`DjangoCacheHandler` bridges this gap.  It wraps any Django cache
backend and converts values to/from strings so that ``StandardTag`` and
``StandardKey`` can store and retrieve tag version counters through
Django's cache infrastructure.

**Typical lifecycle:**

1. :func:`~fragmented_keys_django.config.configure_fragmented_keys` creates a
   ``DjangoCacheHandler`` wrapping the Django cache named in *cache_name*.
2. It registers the handler as the global default via
   ``Configuration.set_default_cache_handler(handler)``.
3. From that point, ``StandardTag("User", "42").get_tag_version()`` calls
   ``handler.get("NOZ:tag:User:42")`` → ``django_cache.get("NOZ:tag:User:42")``
   → returns the version string (or ``None`` on miss).
"""

from __future__ import annotations

import json
import pickle
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.core.cache.backends.base import BaseCache


class DjangoCacheHandler:
    """Adapter between Django cache and fragmented_keys CacheHandler protocol.

    Wraps any Django cache backend and implements the
    ``fragmented_keys.protocols.CacheHandler`` protocol, allowing the
    ``fragmented_keys`` library to work with any Django-compatible cache
    backend (Redis, Memcached, database, LocMemCache, etc.).

    The handler performs automatic type conversion on :meth:`get` — Django
    caches can return ``bytes``, ``dict``, ``list``, ``int``, ``float``, or
    ``bool`` values (especially when the underlying backend uses pickling).
    All are converted to ``str`` for the ``fragmented_keys`` protocol.

    Supports two construction modes:

    - **By name** (delegation): ``DjangoCacheHandler("default")`` — looks up
      an existing Django cache alias from ``settings.CACHES``.
    - **By instance** (standalone): ``DjangoCacheHandler(cache=my_backend)`` —
      wraps a cache backend instance directly, no Django alias required.

    :param cache_name: Name of the Django cache alias to wrap.  Must match
        a key in ``settings.CACHES``.  Ignored if *cache* is provided.
        Default: ``"default"``.
    :param cache: A Django cache backend instance to wrap directly.  When
        provided, *cache_name* is used only for labelling (e.g. in
        :meth:`group_name`), not for lookup.

    :example:

    .. code-block:: python

       from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler
       from fragmented_keys import StandardTag

       # Delegation mode — looks up "default" in settings.CACHES
       handler = DjangoCacheHandler("default")

       # Standalone mode — wraps an existing backend instance
       handler = DjangoCacheHandler(cache=my_redis_backend, cache_name="standalone")

       tag = StandardTag("User", "42", handler=handler)
       version = tag.get_tag_version()
    """

    def __init__(
        self,
        cache_name: str = "default",
        cache: BaseCache | None = None,
    ) -> None:
        if cache is not None:
            self._cache = cache
        else:
            from django.core.cache import caches

            self._cache = caches[cache_name]
        self._cache_name = cache_name

    def group_name(self) -> str:
        """Return a unique identifier for this handler type.

        Used by the ``fragmented_keys`` library to distinguish between
        different cache handler instances (e.g. when multiple handlers
        target different Django cache aliases).

        :returns: String in the format
            ``"DjangoCacheHandler:{backend_class}:{cache_name}"``.
        """
        cache_class_name = self._cache.__class__.__name__
        return f"DjangoCacheHandler:{cache_class_name}:{self._cache_name}"

    def get(self, key: str) -> str | None:
        """Fetch a single value by key, converting to string.

        Implements the ``CacheHandler.get()`` protocol.  Django caches can
        return various Python types depending on the backend and serializer;
        this method normalizes them:

        - ``str`` → returned as-is
        - ``bytes`` → decoded as UTF-8
        - ``dict`` / ``list`` → JSON-serialized
        - ``int`` / ``float`` / ``bool`` → ``str()``
        - anything else → ``str()`` (best-effort)

        :param key: Cache key to fetch.
        :returns: String value, or ``None`` on cache miss.
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
        """Store a string value, optionally with a TTL.

        Implements the ``CacheHandler.set()`` protocol.  The value is stored
        as a plain string through Django's cache API.  The underlying backend
        may further serialize it (e.g. pickle for ``LocMemCache``, raw string
        for ``django-redis``).

        :param key: Cache key to store under.
        :param value: String value to store.
        :param ttl: Time-to-live in seconds.  ``None`` means use the cache
            backend's default timeout.
        """
        self._cache.set(key, value, timeout=ttl)

    def get_multi(self, keys: list[str]) -> dict[str, str]:
        """Fetch multiple values at once, converting each to string.

        Implements the ``CacheHandler.get_multi()`` protocol.  Uses Django's
        ``get_many()`` under the hood for efficient bulk retrieval (single
        round-trip on Redis/Memcached).

        Keys that are not found in the cache are omitted from the returned
        dict.  The same type-conversion logic as :meth:`get` applies to each
        value.

        :param keys: List of cache keys to fetch.
        :returns: Dict mapping found keys to their string values.  Missing
            keys are omitted (not set to ``None``).
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
