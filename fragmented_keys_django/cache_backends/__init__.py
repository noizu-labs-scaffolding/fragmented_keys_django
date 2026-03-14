"""Cache backend implementations for fragmented_keys Django integration.

This sub-package contains:

- :class:`DjangoCacheHandler` — adapts any Django cache backend to the
  :class:`fragmented_keys.protocols.CacheHandler` protocol so that
  ``StandardTag`` and ``StandardKey`` can read/write tag versions through
  Django's cache API.

- :class:`FragmentedKeysCacheBackend` — a Django ``BaseCache`` subclass that
  exposes ``*_with_tags`` methods for tag-aware caching on top of any
  underlying Django cache backend.
"""

from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler
from fragmented_keys_django.cache_backends.django_backend import FragmentedKeysCacheBackend

__all__ = ["DjangoCacheHandler", "FragmentedKeysCacheBackend"]
