"""Django cache backend using fragmented_keys for tag-versioned invalidation.

This module provides :class:`FragmentedKeysCacheBackend`, a Django ``BaseCache``
subclass that layers tag-aware caching on top of any existing Django cache backend.

**Architecture:**

The backend does *not* replace your cache — it wraps it.  You configure it in
``settings.CACHES`` with a ``CACHE_NAME`` pointing to your real cache (e.g.
``"default"``).  Standard ``get``/``set``/``delete`` calls pass through to the
underlying cache.  The ``*_with_tags`` methods compose cache keys that embed
current tag versions, enabling automatic invalidation when tags are incremented.

**Key composition flow** (for ``*_with_tags`` methods):

1. ``_normalize_tags()`` converts input (tuples or ``StandardTag`` objects) into
   a list of ``StandardTag`` instances.
2. ``_build_tagged_key()`` creates a ``StandardKey(key, tag_objs)`` and calls
   ``get_key_str(hash=True)`` — this queries the cache for each tag's current
   version and produces a hashed composite key string.
3. The value is stored/retrieved under this composite key.  When a tag version
   changes, the composite key resolves to a different string → cache miss.

**Configuration in settings.py — two modes:**

*Delegation mode* — wraps an existing Django cache alias:

.. code-block:: python

   CACHES = {
       "default": {
           "BACKEND": "django.core.cache.backends.redis.RedisCache",
           "LOCATION": "redis://127.0.0.1:6379/1",
       },
       "fragmented": {
           "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
           "CACHE_NAME": "default",   # underlying cache alias
           "PREFIX": "NOZ_FRAG",      # global tag prefix
       },
   }

*Standalone mode* — owns its own connection (no separate cache alias needed):

.. code-block:: python

   CACHES = {
       "fragmented": {
           "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
           "LOCATION": "redis://127.0.0.1:6379/1",
           "PREFIX": "NOZ_FRAG",
           # "BACKEND_CLASS": "django.core.cache.backends.redis.RedisCache",  # default
       },
   }

Specifying both ``CACHE_NAME`` and ``LOCATION`` raises ``ValueError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from django.core.cache.backends.base import BaseCache
from django.utils.module_loading import import_string
import warnings

from fragmented_keys import ConstantTag, FragmentedKeyRing, StandardKey, StandardTag
from fragmented_keys.tag.base import BaseTag


class FragmentedKeysCacheBackend(BaseCache):
    """Django cache backend with tag-versioned invalidation.

    Wraps any Django cache backend and adds ``*_with_tags`` methods for
    tag-aware caching.  Standard ``BaseCache`` methods (``get``, ``set``,
    ``delete``, ``get_many``, etc.) pass through to the underlying cache
    unchanged.

    :param params: Django cache backend parameters dict from ``settings.CACHES``.
        Recognized keys:

        **Delegation mode** (wrap an existing Django cache alias):

        - ``CACHE_NAME`` (str): Django cache alias to wrap.  Default: ``"default"``.

        **Standalone mode** (own connection, no separate alias needed):

        - ``LOCATION`` (str): Redis/cache connection URL (e.g.
          ``"redis://127.0.0.1:6379/1"``).
        - ``BACKEND_CLASS`` (str): Dotted path to the real cache backend class.
          Default: ``"django.core.cache.backends.redis.RedisCache"``.

        **Common to both modes:**

        - ``PREFIX`` (str): Global prefix for tag version keys stored in the cache.
          Prevents collisions between apps sharing the same instance.
          Default: ``"NOZ"``.
        - ``OPTIONS`` (dict): Passed through to the underlying backend.

    **Usage:**

    .. code-block:: python

       from django.core.cache import caches

       frag = caches["fragmented"]

       # Standard API (pass-through, no tags)
       frag.set("plain_key", data)

       # Tag-aware API (composite keys with automatic invalidation)
       frag.set_with_tags("profile", data, [("User", "42")], timeout=3600)
       frag.get_with_tags("profile", [("User", "42")])

       # Invalidate: bumps tag version so all dependent keys miss
       frag.invalidate_tags([("User", "42")])
    """

    def __init__(self, server: str, params: dict[str, Any]) -> None:
        super().__init__(params)
        self._prefix = params.get("PREFIX", "NOZ")
        self._options = params.get("OPTIONS", {})

        cache_name = params.get("CACHE_NAME")
        location = server or params.get("LOCATION")

        if cache_name and location:
            raise ValueError(
                "FragmentedKeysCacheBackend: specify either CACHE_NAME (delegation "
                "mode) or LOCATION (standalone mode), not both."
            )

        from fragmented_keys import Configuration
        from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

        if location:
            # Standalone mode — instantiate the underlying backend directly
            self._cache_name = params.get("CACHE_NAME", "standalone")
            backend_class = params.get(
                "BACKEND_CLASS", "django.core.cache.backends.redis.RedisCache"
            )
            cls = import_string(backend_class)
            underlying = cls(location, params)
            self._handler = DjangoCacheHandler(
                cache_name=self._cache_name, cache=underlying
            )
        else:
            # Delegation mode — wrap an existing Django cache alias
            self._cache_name = cache_name or "default"
            self._handler = DjangoCacheHandler(self._cache_name)

        Configuration.set_default_cache_handler(self._handler)
        Configuration.set_global_prefix(self._prefix)

    # ── Standard BaseCache methods (pass-through) ─────────────────

    def add(self, key: str, value: Any, timeout: int | None = None, version: int | None = None) -> bool:
        """Add a value only if the key doesn't already exist.

        Pass-through to the underlying cache — no tag composition.

        :param key: Cache key.
        :param value: Value to store.
        :param timeout: TTL in seconds.
        :param version: Django cache version (integer, not tag version).
        :returns: ``True`` if the key was added, ``False`` if it already existed.
        """
        cache_key = self.make_key(key, version)
        return self._handler._cache.add(cache_key, value, timeout=timeout)

    def get(self, key: str, default: Any = None, version: int | None = None) -> Any:
        """Fetch a value from the cache.

        Pass-through to the underlying cache — no tag composition.

        :param key: Cache key.
        :param default: Value to return on cache miss.
        :param version: Django cache version.
        :returns: Cached value, or *default* if not found.
        """
        cache_key = self.make_key(key, version)
        val = self._handler._cache.get(cache_key)
        return val if val is not None else default

    def set(self, key: str, value: Any, timeout: int | None = None, version: int | None = None) -> bool:
        """Store a value in the cache.

        Pass-through to the underlying cache — no tag composition.

        :param key: Cache key.
        :param value: Value to store.
        :param timeout: TTL in seconds.
        :param version: Django cache version.
        :returns: ``True`` on success.
        """
        cache_key = self.make_key(key, version)
        self._handler._cache.set(cache_key, value, timeout=timeout)
        return True

    def touch(self, key: str, timeout: int | None = None, version: int | None = None) -> bool:
        """Update the timeout for a key without changing its value.

        :param key: Cache key.
        :param timeout: New TTL in seconds.
        :param version: Django cache version.
        :returns: ``True`` on success, ``False`` if the backend doesn't support ``touch``.
        """
        cache_key = self.make_key(key, version)
        try:
            self._handler._cache.touch(cache_key, timeout)
            return True
        except (AttributeError, NotImplementedError):
            # Some cache backends don't support touch (e.g., database cache)
            return False

    def delete(self, key: str, version: int | None = None) -> bool:
        """Delete a key from the cache.

        :param key: Cache key.
        :param version: Django cache version.
        :returns: ``True`` (always, matching Django convention).
        """
        cache_key = self.make_key(key, version)
        self._handler._cache.delete(cache_key)
        return True

    def get_many(self, keys: list[str], version: int | None = None) -> dict[str, Any]:
        """Fetch multiple keys from the cache.

        Uses the underlying cache's ``get_many`` for efficient bulk retrieval.

        :param keys: List of cache keys.
        :param version: Django cache version.
        :returns: Dict mapping found keys (original names, not make_key'd) to values.
        """
        key_map = {self.make_key(key, version): key for key in keys}
        results = self._handler._cache.get_many(list(key_map.keys()))
        # Reverse the key transformation for the result
        return {key_map[k]: v for k, v in results.items() if k in key_map}

    def get_or_set(self, key: str, default: Any, timeout: int | None = None, version: int | None = None) -> Any:
        """Fetch a value, or store *default* if the key doesn't exist.

        :param key: Cache key.
        :param default: Value to store on miss (not callable — use
            :meth:`get_or_set_with_tags` for callable defaults).
        :param timeout: TTL in seconds.
        :param version: Django cache version.
        :returns: The cached or newly-stored value.
        """
        cache_key = self.make_key(key, version)
        val = self._handler._cache.get(cache_key)
        if val is not None:
            return val
        self._handler._cache.set(cache_key, default, timeout=timeout)
        return default

    def set_many(self, data: dict[str, Any], timeout: int | None = None, version: int | None = None) -> list[str]:
        """Set multiple keys in the cache.

        :param data: Dict mapping cache keys to values.
        :param timeout: TTL in seconds.
        :param version: Django cache version.
        :returns: Empty list (Django convention for success).
        """
        cache_data = {self.make_key(k, version): v for k, v in data.items()}
        self._handler._cache.set_many(cache_data, timeout=timeout)
        return []  # Django's set_many always returns empty list for success

    def delete_many(self, keys: list[str], version: int | None = None) -> None:
        """Delete multiple keys from the cache.

        :param keys: List of cache keys.
        :param version: Django cache version.
        """
        cache_keys = [self.make_key(key, version) for key in keys]
        self._handler._cache.delete_many(cache_keys)

    def has_key(self, key: str, version: int | None = None) -> bool:
        """Check if a key exists in the cache.

        :param key: Cache key.
        :param version: Django cache version.
        :returns: ``True`` if the key exists.
        """
        cache_key = self.make_key(key, version)
        return self._handler._cache.has_key(cache_key)  # noqa: E501

    def clear(self) -> None:
        """Clear all keys from the underlying cache.

        .. warning::

           This clears the *entire* underlying cache, not just fragmented-key
           entries.  If other applications share the same cache, their data
           will be lost too.
        """
        self._handler._cache.clear()

    def incr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        """Atomically increment a key's integer value.

        :param key: Cache key.
        :param delta: Amount to increment by.
        :param version: Django cache version.
        :returns: New value after increment.
        :raises ValueError: If the key does not exist.
        """
        if not self.has_key(key, version):
            raise ValueError(f"Key '{key}' not found")
        return self._handler._cache.incr(self.make_key(key, version), delta)

    def decr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        """Atomically decrement a key's integer value.

        :param key: Cache key.
        :param delta: Amount to decrement by.
        :param version: Django cache version.
        :returns: New value after decrement.
        :raises ValueError: If the key does not exist.
        """
        if not self.has_key(key, version):
            raise ValueError(f"Key '{key}' not found")
        return self._handler._cache.decr(self.make_key(key, version), delta)

    def close(self, **kwargs: Any) -> None:
        """Close the cache connection if the underlying backend supports it."""
        try:
            self._handler._cache.close(**kwargs)
        except (AttributeError, NotImplementedError):
            pass

    def get_backend_timeout(self, timeout: int | None) -> int | None:
        """Return the timeout value to use for the cache backend.

        :param timeout: Requested timeout, or ``None`` to use the default.
        :returns: Resolved timeout in seconds.
        """
        if timeout is None:
            return self.default_timeout
        return timeout

    # ── Tag-aware API ──────────────────────────────────────────────

    def _normalize_tags(
        self, tags: list[tuple | BaseTag | dict],
    ) -> list[BaseTag]:
        """Convert mixed tag inputs into a uniform list of tag objects.

        Accepted input forms:

        - ``BaseTag`` subclass instances (``StandardTag``, ``ConstantTag``, or
          custom) — passed through unchanged.
        - ``(name, instance)`` 2-tuple — ``StandardTag(name, instance)``.
        - ``(name,)`` 1-tuple — ``StandardTag(name, "*")``.
          Emits a ``DeprecationWarning`` suggesting an explicit 2-tuple.
        - ``(name, instance, "constant")`` 3-tuple — ``ConstantTag(name, instance)``.
        - ``dict`` with keys ``tag``, ``instance``, and optional ``type``
          (``"standard"`` or ``"constant"``), ``version`` — full control form.

        :param tags: List of tags in any supported form.
        :returns: List of ``BaseTag`` subclass instances.
        :raises TypeError: If an element doesn't match any accepted form.
        """
        result: list[BaseTag] = []
        for tag in tags:
            if isinstance(tag, BaseTag):
                result.append(tag)
            elif isinstance(tag, dict):
                result.append(self._tag_from_dict(tag))
            elif isinstance(tag, tuple):
                result.append(self._tag_from_tuple(tag))
            else:
                raise TypeError(
                    f"Tags must be BaseTag instances, tuples, or dicts, got {type(tag)}"
                )
        return result

    def _tag_from_tuple(self, tag: tuple) -> BaseTag:
        if len(tag) == 1:
            warnings.warn(
                f"1-tuple tag ({tag[0]!r},) is deprecated. "
                f"Use an explicit 2-tuple ('{tag[0]}', '<scope_id>') instead.",
                DeprecationWarning,
                stacklevel=4,
            )
            return StandardTag(str(tag[0]), "*", handler=self._handler)
        elif len(tag) == 2:
            name, instance = tag
            return StandardTag(str(name), str(instance), handler=self._handler)
        elif len(tag) == 3:
            name, instance, tag_type = tag
            if str(tag_type).lower() == "constant":
                return ConstantTag(str(name), str(instance), handler=self._handler)
            raise TypeError(
                f"3-tuple tag type must be 'constant', got {tag_type!r}"
            )
        raise TypeError(
            f"Tag tuples must be 1-, 2-, or 3-element, got {len(tag)}-element"
        )

    def _tag_from_dict(self, tag: dict) -> BaseTag:
        tag_name = str(tag["tag"])
        instance = str(tag.get("instance", ""))
        tag_type = str(tag.get("type", "standard")).lower()
        version = tag.get("version")

        if tag_type == "constant":
            return ConstantTag(
                tag_name, instance,
                version=float(version) if version is not None else 1.0,
                handler=self._handler,
            )
        return StandardTag(
            tag_name, instance,
            version=float(version) if version is not None else None,
            handler=self._handler,
        )

    def _build_tagged_key(
        self,
        key: str,
        tags: list[tuple[str, str] | StandardTag],
        group_id: str = "",
    ) -> str:
        """Build a composite cache key string from a base key + tags.

        Creates a ``StandardKey``, queries Redis for each tag's current version,
        and returns a hashed key string.  The key changes whenever any tag
        version changes — this is the core invalidation mechanism.

        :param key: Base cache key name (human-readable, e.g. ``"user_profile"``).
        :param tags: List of tags (tuples or ``StandardTag`` objects).
        :param group_id: Optional group identifier for namespacing keys that share
            the same base name and tags.
        :returns: Hashed composite key string ready for use with the underlying cache.
        """
        tag_objs = self._normalize_tags(tags)
        std_key = StandardKey(key, tag_objs, group_id=group_id)
        return std_key.get_key_str(hash=True)

    def set_with_tags(
        self,
        key: str,
        value: Any,
        tags: list[tuple[str, str] | StandardTag],
        timeout: int | None = None,
        group_id: str = "",
    ) -> bool:
        """Store a value using a tag-composed composite key.

        The cache key is composed from *key* + current versions of all *tags*.
        When any tag is later incremented, future lookups with the same *key*
        and *tags* will compose a different cache key → automatic miss.

        :param key: Base cache key name.
        :param value: Value to cache (any picklable object).
        :param tags: List of ``StandardTag`` objects or ``(name, instance)`` tuples.
        :param timeout: Cache TTL in seconds.
        :param group_id: Optional group identifier (see :meth:`_build_tagged_key`).
        :returns: ``True`` on success.

        :example:

        .. code-block:: python

           frag.set_with_tags("profile", user_data, [("User", "42")], timeout=3600)
        """
        cache_key = self._build_tagged_key(key, tags, group_id)
        self._handler._cache.set(cache_key, value, timeout=timeout)
        return True

    def get_with_tags(
        self,
        key: str,
        tags: list[tuple[str, str] | StandardTag],
        default: Any = None,
        group_id: str = "",
    ) -> Any:
        """Fetch a value using a tag-composed composite key.

        Composes the same key that :meth:`set_with_tags` would produce for the
        given *key* + *tags* + *group_id* combination, then looks it up.  If
        any tag version has changed since the value was stored, the composed key
        differs and this returns *default* (cache miss).

        :param key: Base cache key name.
        :param tags: List of ``StandardTag`` objects or ``(name, instance)`` tuples.
        :param default: Value to return on cache miss.
        :param group_id: Optional group identifier.
        :returns: Cached value, or *default* on miss.
        """
        cache_key = self._build_tagged_key(key, tags, group_id)
        val = self._handler._cache.get(cache_key)
        return val if val is not None else default

    def get_or_set_with_tags(
        self,
        key: str,
        default: Any,
        tags: list[tuple[str, str] | StandardTag],
        timeout: int | None = None,
        group_id: str = "",
    ) -> Any:
        """Fetch a value, or compute and store it on cache miss.

        Like :meth:`get_with_tags` but if the key is not found, stores
        *default* (or its return value if callable) and returns it.

        When *default* is a callable (e.g. a lambda or function), it is only
        called on cache miss.  This avoids running expensive queries when the
        cache already has the value.

        :param key: Base cache key name.
        :param default: Value to store on miss, or a callable that returns it.
        :param tags: List of ``StandardTag`` objects or ``(name, instance)`` tuples.
        :param timeout: Cache TTL in seconds.
        :param group_id: Optional group identifier.
        :returns: The cached or newly-computed value.

        :example:

        .. code-block:: python

           data = frag.get_or_set_with_tags(
               "profile",
               lambda: expensive_query(42),  # only called on miss
               [("User", "42")],
               timeout=3600,
           )
        """
        cache_key = self._build_tagged_key(key, tags, group_id)
        val = self._handler._cache.get(cache_key)
        if val is not None:
            return val
        value = default() if callable(default) else default
        self._handler._cache.set(cache_key, value, timeout=timeout)
        return value

    def delete_with_tags(
        self,
        key: str,
        tags: list[tuple[str, str] | StandardTag],
        group_id: str = "",
    ) -> bool:
        """Delete a specific composite cache entry by key + tags.

        Composes the same key that :meth:`set_with_tags` would produce and
        deletes it from the underlying cache.

        .. note::

           In normal operation you rarely need this — incrementing a tag via
           :meth:`invalidate_tags` makes old entries unreachable without
           deleting them.  Use this only when you need to free memory
           immediately.

        :param key: Base cache key name.
        :param tags: List of ``StandardTag`` objects or ``(name, instance)`` tuples.
        :param group_id: Optional group identifier.
        :returns: ``True`` (always).
        """
        cache_key = self._build_tagged_key(key, tags, group_id)
        self._handler._cache.delete(cache_key)
        return True

    def invalidate_tags(
        self, tags: list[tuple[str, str] | StandardTag],
    ) -> int:
        """Increment tag versions to invalidate all dependent cache entries.

        This is the primary invalidation mechanism.  It does *not* delete any
        cached values — it bumps the version counter for each tag so that all
        future key compositions produce different strings → cache misses.
        Old entries expire naturally via their TTL.

        :param tags: List of ``StandardTag`` objects or ``(name, instance)`` tuples.
        :returns: Number of tags that were incremented.

        :example:

        .. code-block:: python

           # Invalidate everything tagged with User:42
           frag.invalidate_tags([("User", "42")])

           # Invalidate multiple tags at once
           frag.invalidate_tags([("User", "42"), ("Campaign", "99")])
        """
        tag_objs = self._normalize_tags(tags)
        for tag in tag_objs:
            tag.increment()
        return len(tag_objs)

    # ── Introspection ──────────────────────────────────────────────

    def get_tag_version(self, tag_name: str, instance: str = "") -> float:
        """Read the current version counter for a tag.

        Useful for debugging and verifying that invalidation has occurred.
        The version is a monotonically increasing float stored in the
        underlying cache under a key like ``{PREFIX}:tag:{tag_name}:{instance}``.

        :param tag_name: The tag name (e.g. ``"User"``).
        :param instance: The tag instance identifier (e.g. ``"42"``).
        :returns: Current version as a float.  Returns ``0.0`` if the tag
            has never been set.
        """
        tag = StandardTag(tag_name, instance, handler=self._handler)
        return tag.get_tag_version()

    def create_key_ring(self, **kwargs: Any) -> FragmentedKeyRing:
        """Create a :class:`FragmentedKeyRing` pre-configured with this backend.

        The returned key ring uses this backend's :class:`DjangoCacheHandler`
        and prefix, saving you from passing them in manually.  Useful for
        advanced patterns where you manage multiple related keys as a group.

        :param kwargs: Additional keyword arguments forwarded to
            ``FragmentedKeyRing.__init__``.  ``cache_handlers``,
            ``default_cache_handler``, and ``default_prefix`` are set
            automatically if not provided.
        :returns: Configured :class:`FragmentedKeyRing` instance.
        """
        kwargs.setdefault("cache_handlers", {"django": self._handler})
        kwargs.setdefault("default_cache_handler", "django")
        kwargs.setdefault("default_prefix", self._prefix)
        return FragmentedKeyRing(**kwargs)
