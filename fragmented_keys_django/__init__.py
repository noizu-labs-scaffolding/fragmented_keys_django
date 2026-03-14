"""Django integration for the fragmented-keys library.

Provides tag-versioned cache invalidation for Django applications. Cache keys
embed current tag versions; when a tag is incremented (e.g. on model save),
all dependent keys resolve to new strings — automatic cache miss, automatic
recomputation, no explicit deletes.

Two usage modes:

**Decorator mode** — wrap functions with :func:`tagged_cache`::

    @tagged_cache(timeout=3600, tags=["User:{user_id}"], vary_on=["user_id"])
    def get_profile(user_id: int):
        return User.objects.get(pk=user_id).profile

**Backend mode** — use :class:`FragmentedKeysCacheBackend` in ``CACHES`` and call
``*_with_tags`` methods directly::

    frag = caches["fragmented"]
    data = frag.get_or_set_with_tags("profile", loader, [("User", "42")], timeout=3600)

Key components:

- :func:`~fragmented_keys_django.config.configure_fragmented_keys` — one-call global setup
- :class:`~fragmented_keys_django.cache_utils.decorators.tagged_cache` — decorator for per-function caching
- :class:`~fragmented_keys_django.cache_utils.model_helpers.ModelTagManager` — signal-driven auto-invalidation
- :class:`~fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend` — Django cache backend
- :func:`~fragmented_keys_django.cache_utils.tags.model_tag`,
  :func:`~fragmented_keys_django.cache_utils.tags.list_tag`,
  :func:`~fragmented_keys_django.cache_utils.tags.aggregate_tag` — tag factory functions
"""

__version__ = "0.1.0"
