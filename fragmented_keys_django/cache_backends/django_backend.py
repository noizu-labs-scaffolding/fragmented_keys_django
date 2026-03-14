"""Django cache backend using fragmented_keys for automatic invalidation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from django.core.cache.backends.base import BaseCache
from fragmented_keys import FragmentedKeyRing, StandardKey, StandardTag


class FragmentedKeysCacheBackend(BaseCache):
    """Django cache backend using fragmented_keys for automatic invalidation.

    This backend wraps any other Django cache backend and uses fragmented_keys
    to automatically invalidate cache entries when tags are incremented.

    Usage in settings.py:
        CACHES = {
            "fragmented": {
                "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
                "CACHE_NAME": "default",  # Underlying Django cache to use
                "PREFIX": "NOZ_FRAG",    # Global prefix for tags
            }
        }

    Then use Django's cache API normally:
        from django.core.cache import cache
        result = cache.get('my_key')
        cache.set('my_key', data, timeout=3600)
    """

    def __init__(self, params: dict[str, Any]) -> None:
        """Initialize the cache backend.

        Args:
            params: Django cache backend parameters including:
                - CACHE_NAME: Underlying Django cache to use (default: "default")
                - PREFIX: Global prefix for fragmented_keys tags (default: "NOZ")
        """
        super().__init__(params)
        self._cache_name = params.get("CACHE_NAME", "default")
        self._prefix = params.get("PREFIX", "NOZ")
        self._options = params.get("OPTIONS", {})

        from fragmented_keys import Configuration
        from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

        # Configure fragmented_keys with Django cache handler
        self._handler = DjangoCacheHandler(self._cache_name)
        Configuration.set_default_cache_handler(self._handler)
        Configuration.set_global_prefix(self._prefix)

    def add(self, key: str, value: Any, timeout: int | None = None, version: int | None = None) -> bool:
        """Add a value to the cache if the key doesn't already exist.

        Returns False if the key already exists.
        """
        cache_key = self.make_key(key, version)
        return self._handler._cache.add(cache_key, value, timeout=timeout)

    def get(self, key: str, default: Any = None, version: int | None = None) -> Any:
        """Fetch a value from the cache. Returns default if not found."""
        cache_key = self.make_key(key, version)
        val = self._handler._cache.get(cache_key)
        return val if val is not None else default

    def set(self, key: str, value: Any, timeout: int | None = None, version: int | None = None) -> bool:
        """Store a value in the cache. Returns True on success."""
        cache_key = self.make_key(key, version)
        self._handler._cache.set(cache_key, value, timeout=timeout)
        return True

    def touch(self, key: str, timeout: int | None = None, version: int | None = None) -> bool:
        """Update the timeout for a key without changing its value."""
        cache_key = self.make_key(key, version)
        try:
            self._handler._cache.touch(cache_key, timeout)
            return True
        except (AttributeError, NotImplementedError):
            # Some cache backends don't support touch (e.g., database cache)
            return False

    def delete(self, key: str, version: int | None = None) -> bool:
        """Delete a key from the cache."""
        cache_key = self.make_key(key, version)
        self._handler._cache.delete(cache_key)
        return True

    def get_many(self, keys: list[str], version: int | None = None) -> dict[str, Any]:
        """Fetch multiple keys from the cache."""
        key_map = {self.make_key(key, version): key for key in keys}
        results = self._handler._cache.get_many(list(key_map.keys()))
        # Reverse the key transformation for the result
        return {key_map[k]: v for k, v in results.items() if k in key_map}

    def get_or_set(self, key: str, default: Any, timeout: int | None = None, version: int | None = None) -> Any:
        """Fetch a value from the cache, or set it if it doesn't exist."""
        cache_key = self.make_key(key, version)
        val = self._handler._cache.get(cache_key)
        if val is not None:
            return val
        self._handler._cache.set(cache_key, default, timeout=timeout)
        return default

    def set_many(self, data: dict[str, Any], timeout: int | None = None, version: int | None = None) -> list[str]:
        """Set multiple keys in the cache."""
        cache_data = {self.make_key(k, version): v for k, v in data.items()}
        self._handler._cache.set_many(cache_data, timeout=timeout)
        return []  # Django's set_many always returns empty list for success

    def delete_many(self, keys: list[str], version: int | None = None) -> None:
        """Delete multiple keys from the cache."""
        cache_keys = [self.make_key(key, version) for key in keys]
        self._handler._cache.delete_many(cache_keys)

    def has_key(self, key: str, version: int | None = None) -> bool:
        """Check if a key exists in the cache."""
        cache_key = self.make_key(key, version)
        return self._handler._cache.has_key(cache_key)  # noqa: E501

    def clear(self) -> None:
        """Clear all keys from the cache."""
        self._handler._cache.clear()

    def incr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        """Increment a key's value."""
        if not self.has_key(key, version):
            raise ValueError(f"Key '{key}' not found")
        return self._handler._cache.incr(self.make_key(key, version), delta)

    def decr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        """Decrement a key's value."""
        if not self.has_key(key, version):
            raise ValueError(f"Key '{key}' not found")
        return self._handler._cache.decr(self.make_key(key, version), delta)

    def close(self, **kwargs: Any) -> None:
        """Close the cache connection if applicable."""
        try:
            self._handler._cache.close(**kwargs)
        except (AttributeError, NotImplementedError):
            pass

    def get_backend_timeout(self, timeout: int | None) -> int | None:
        """Return the timeout value to use for the cache backend."""
        if timeout is None:
            return self.default_timeout
        return timeout

    # ── Tag-aware API ──────────────────────────────────────────────

    def _normalize_tags(
        self, tags: list[tuple[str, str] | StandardTag],
    ) -> list[StandardTag]:
        """Convert mixed tag inputs into a list of StandardTag objects.

        Accepts:
            - StandardTag instances (passed through)
            - (name, instance) tuples (converted to StandardTag)

        Raises TypeError for anything else.
        """
        result: list[StandardTag] = []
        for tag in tags:
            if isinstance(tag, StandardTag):
                result.append(tag)
            elif isinstance(tag, tuple) and len(tag) == 2:
                name, instance = tag
                result.append(StandardTag(str(name), str(instance), handler=self._handler))
            else:
                raise TypeError(
                    f"Tags must be StandardTag instances or (name, instance) tuples, got {type(tag)}"
                )
        return result

    def _build_tagged_key(
        self,
        key: str,
        tags: list[tuple[str, str] | StandardTag],
        group_id: str = "",
    ) -> str:
        """Build a composite cache key string from key + tags.

        Returns the hashed composite key string.
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
        """Set a value using a tag-composed composite key.

        Args:
            key: Base cache key name.
            value: Value to cache.
            tags: List of StandardTag objects or (name, instance) tuples.
            timeout: Cache timeout in seconds.
            group_id: Optional group identifier.
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
        """Get a value using a tag-composed composite key.

        Args:
            key: Base cache key name.
            tags: List of StandardTag objects or (name, instance) tuples.
            default: Value to return on cache miss.
            group_id: Optional group identifier.
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
        """Get a value or set it if missing, using tag-composed key.

        Args:
            key: Base cache key name.
            default: Value to set on miss (can be a callable).
            tags: List of StandardTag objects or (name, instance) tuples.
            timeout: Cache timeout in seconds.
            group_id: Optional group identifier.
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
        """Delete a specific composite entry by key + tags.

        Args:
            key: Base cache key name.
            tags: List of StandardTag objects or (name, instance) tuples.
            group_id: Optional group identifier.
        """
        cache_key = self._build_tagged_key(key, tags, group_id)
        self._handler._cache.delete(cache_key)
        return True

    def invalidate_tags(
        self, tags: list[tuple[str, str] | StandardTag],
    ) -> int:
        """Increment tag versions to invalidate all dependent entries.

        Args:
            tags: List of StandardTag objects or (name, instance) tuples.

        Returns:
            Number of tags invalidated.
        """
        tag_objs = self._normalize_tags(tags)
        for tag in tag_objs:
            tag.increment()
        return len(tag_objs)

    # ── Introspection ──────────────────────────────────────────────

    def get_tag_version(self, tag_name: str, instance: str = "") -> float:
        """Get the current version of a tag (useful for debugging).

        Args:
            tag_name: The tag name.
            instance: The tag instance identifier.

        Returns:
            Current tag version as a float.
        """
        tag = StandardTag(tag_name, instance, handler=self._handler)
        return tag.get_tag_version()

    def create_key_ring(self, **kwargs: Any) -> FragmentedKeyRing:
        """Create a FragmentedKeyRing pre-configured with this backend's handler and prefix.

        Any kwargs are forwarded to the FragmentedKeyRing constructor,
        with defaults for cache_handlers and default_prefix taken from
        this backend's configuration.
        """
        kwargs.setdefault("cache_handlers", {"django": self._handler})
        kwargs.setdefault("default_cache_handler", "django")
        kwargs.setdefault("default_prefix", self._prefix)
        return FragmentedKeyRing(**kwargs)