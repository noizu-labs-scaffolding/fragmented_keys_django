"""Cache utilities for Django-fragmented_keys integration.

This sub-package contains:

- :func:`tagged_cache` — decorator that wraps a function with tag-versioned
  caching.  Builds a composite cache key from tag versions + function arguments,
  checks the cache, and only calls the function on a miss.

- :class:`ModelTagManager` — registers Django models for automatic cache
  invalidation via ``post_save`` / ``post_delete`` signals.  When a registered
  model instance is saved or deleted, its tag version is incremented.

- :func:`model_tag`, :func:`list_tag`, :func:`aggregate_tag` — semantic factory
  functions that create ``StandardTag`` instances.  They are behaviorally identical;
  the different names communicate intent to future readers.
"""

from fragmented_keys_django.cache_utils.decorators import tagged_cache
from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager
from fragmented_keys_django.cache_utils.tags import aggregate_tag, list_tag, model_tag

__all__ = ["ModelTagManager", "aggregate_tag", "list_tag", "model_tag", "tagged_cache"]
