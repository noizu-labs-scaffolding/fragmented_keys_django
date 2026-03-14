"""Configuration utilities for fragmented_keys Django integration.

This module provides one-call setup functions for wiring the ``fragmented_keys``
library into Django.  The typical entry point is :func:`configure_fragmented_keys`,
called once in ``AppConfig.ready()``.

**Initialization flow:**

1. :func:`configure_fragmented_keys` creates a :class:`DjangoCacheHandler` wrapping
   a named Django cache (e.g. ``"default"``).
2. It sets this handler as the global default via
   ``Configuration.set_default_cache_handler()`` — so every ``StandardTag`` and
   ``StandardKey`` created afterwards uses your Django cache for version storage
   without needing an explicit handler argument.
3. It sets the global prefix via ``Configuration.set_global_prefix()`` — this
   namespaces all tag version keys in Redis (e.g. ``NOZ:tag:User:42``) so multiple
   apps sharing the same Redis instance don't collide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


def configure_fragmented_keys(
    cache_name: str = "default",
    prefix: str = "NOZ",
    global_prefix: str | None = None,
) -> None:
    """Configure fragmented_keys global settings.

    This is the primary setup function.  Call it once during application
    initialization — typically in ``AppConfig.ready()`` — to wire the
    ``fragmented_keys`` library into Django's cache infrastructure.

    Internally this does two things:

    1. Creates a :class:`~fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler`
       wrapping the Django cache identified by *cache_name* and registers it as the
       global default handler.  After this call, ``StandardTag("User", "42")`` will
       read/write its version counter through your Django cache without needing an
       explicit ``handler=`` argument.

    2. Sets the global prefix to *prefix*.  The prefix is prepended to every tag
       version key stored in the cache backend (e.g. ``NOZ:tag:User:42``), preventing
       collisions when multiple applications share the same Redis instance.

    :param cache_name: Name of the Django cache alias to use as the backing store
        (must match a key in ``settings.CACHES``).  Default: ``"default"``.
    :param prefix: Global prefix for all tag version keys.  Default: ``"NOZ"``.
    :param global_prefix: Alias for *prefix* (backward compatibility).  If both
        are provided, *global_prefix* takes precedence.

    :example:

    .. code-block:: python

       # myapp/apps.py
       from django.apps import AppConfig

       class MyAppConfig(AppConfig):
           name = "myapp"

           def ready(self):
               from fragmented_keys_django import configure_fragmented_keys
               configure_fragmented_keys(cache_name="default", prefix="MYAPP")
    """
    from fragmented_keys import Configuration
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    # Support both parameter names for convenience
    actual_prefix = global_prefix or prefix

    handler = DjangoCacheHandler(cache_name)
    Configuration.set_default_cache_handler(handler)
    Configuration.set_global_prefix(actual_prefix)


def get_cache_handler(cache_name: str = "default"):
    """Get a configured Django cache handler without modifying global state.

    Use this when you need a :class:`DjangoCacheHandler` for a specific Django
    cache alias *without* changing the global default handler.  Useful for
    constructing ``StandardTag`` or ``StandardKey`` objects that should target
    a different cache than the globally-configured one.

    :param cache_name: Django cache alias (must match a key in ``settings.CACHES``).
    :returns: A :class:`~fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler` instance.

    :example:

    .. code-block:: python

       from fragmented_keys import StandardTag
       from fragmented_keys_django.config import get_cache_handler

       handler = get_cache_handler("redis_cache")
       tag = StandardTag("MyTag", "instance", handler=handler)
    """
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    return DjangoCacheHandler(cache_name)


def reset_configuration() -> None:
    """Reset fragmented_keys configuration to defaults.

    Clears the global default cache handler and prefix by calling
    ``Configuration.reset()`` on the upstream ``fragmented_keys`` library.

    Primarily useful in **test teardowns** to ensure a clean state between
    test cases.  Without this, tag versions written by one test could leak
    into another.

    :example:

    .. code-block:: python

       from fragmented_keys_django.config import reset_configuration

       class CacheTestCase(TestCase):
           def setUp(self):
               reset_configuration()
    """
    from fragmented_keys import Configuration

    Configuration.reset()


def set_cache_handler_globally(cache_name: str) -> None:
    """Replace the global cache handler with one targeting a different Django cache.

    Creates a new :class:`DjangoCacheHandler` wrapping *cache_name* and sets it
    as the global default.  Use this when you need to switch the backing cache
    after initial configuration (e.g. in tests or multi-tenant setups).

    :param cache_name: Django cache alias to use.

    :example:

    .. code-block:: python

       from fragmented_keys_django.config import set_cache_handler_globally
       set_cache_handler_globally("memcached_cache")
    """
    from fragmented_keys import Configuration
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    handler = DjangoCacheHandler(cache_name)
    Configuration.set_default_cache_handler(handler)


def set_global_prefix(prefix: str) -> None:
    """Change the global prefix for all tag version keys.

    The prefix is prepended to every tag version key stored in the cache
    backend.  Changing it effectively makes all previously-stored tag versions
    unreachable (equivalent to a full cache bust for tag-based caching).

    :param prefix: New global prefix string.

    :example:

    .. code-block:: python

       from fragmented_keys_django.config import set_global_prefix
       set_global_prefix("PRODUCTION")
    """
    from fragmented_keys import Configuration

    Configuration.set_global_prefix(prefix)


def get_global_prefix() -> str:
    """Return the current global prefix for tag version keys.

    :returns: Current global prefix string.
    """
    from fragmented_keys import Configuration

    return Configuration.get_global_prefix()
