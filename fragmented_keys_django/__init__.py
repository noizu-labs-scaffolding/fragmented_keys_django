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
"""

__version__ = "0.1.5"

from fragmented_keys_django.config import configure_fragmented_keys, reset_configuration
from fragmented_keys_django.cache_utils.decorators import tagged_cache
from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager
from fragmented_keys_django.cache_backends.django_backend import FragmentedKeysCacheBackend
from fragmented_keys_django.cache_utils.tags import model_tag, list_tag, aggregate_tag

__all__ = [
    "configure_fragmented_keys",
    "reset_configuration",
    "tagged_cache",
    "ModelTagManager",
    "FragmentedKeysCacheBackend",
    "model_tag",
    "list_tag",
    "aggregate_tag",
]
