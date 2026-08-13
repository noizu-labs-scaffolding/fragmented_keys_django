"""Django integration for the fragmented-keys library.

Provides tag-versioned cache invalidation for Django applications. Cache keys
embed current tag versions; when a tag is incremented (e.g. on model save),
all dependent keys resolve to new strings — automatic cache miss, automatic
recomputation, no explicit deletes.

Three usage modes:

**Decorator mode** — wrap functions with :func:`tagged_cache`::

    @tagged_cache(timeout=3600, tags=["User:{user_id}"], vary_on=["user_id"])
    def get_profile(user_id: int):
        return User.objects.get(pk=user_id).profile

**Backend mode** — use :class:`FragmentedKeysCacheBackend` in ``CACHES`` and call
``*_with_tags`` methods directly::

    frag = caches["fragmented"]
    data = frag.get_or_set_with_tags("profile", loader, [("User", "42")], timeout=3600)

**KeyRing mode** — define key templates centrally, use them in views::

    ring = get_key_ring("default")
    ring.define_key("profile", ["user"])
    key = ring.get_profile_key_obj("42")
"""

__version__ = "0.2.1"

from fragmented_keys import ConstantTag, FragmentedKeyRing, MemoryHandler

from fragmented_keys_django.config import configure_fragmented_keys, reset_configuration
from fragmented_keys_django.cache_utils.decorators import tagged_cache
from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager
from fragmented_keys_django.cache_backends.django_backend import FragmentedKeysCacheBackend
from fragmented_keys_django.cache_utils.tags import (
    model_tag, list_tag, aggregate_tag, constant_tag, custom_tag,
)
from fragmented_keys_django.cache_utils.key_rings import (
    register_key_ring, get_key_ring, clear_key_rings,
)
from fragmented_keys_django.cache_utils.bulk import (
    CacheAwareManager, CacheAwareQuerySet,
)
from fragmented_keys_django.cache_utils.epoch import (
    get_cache_epoch, set_cache_epoch, epoch_tag, with_epoch,
)

__all__ = [
    # Config
    "configure_fragmented_keys",
    "reset_configuration",
    # Decorators
    "tagged_cache",
    # Model invalidation
    "ModelTagManager",
    # Backend
    "FragmentedKeysCacheBackend",
    # Tag factories
    "model_tag",
    "list_tag",
    "aggregate_tag",
    "constant_tag",
    "custom_tag",
    # Core re-exports
    "ConstantTag",
    "FragmentedKeyRing",
    "MemoryHandler",
    # KeyRing registry
    "register_key_ring",
    "get_key_ring",
    "clear_key_rings",
    # Bulk operation support
    "CacheAwareManager",
    "CacheAwareQuerySet",
    # Global cache epoch
    "get_cache_epoch",
    "set_cache_epoch",
    "epoch_tag",
    "with_epoch",
]
