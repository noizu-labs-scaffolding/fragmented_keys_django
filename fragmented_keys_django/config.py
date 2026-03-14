"""Configuration utilities for fragmented_keys Django integration."""

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

    This function sets up the fragmented_keys library with a Django
    cache handler and global prefix. It should be called once during
    application initialization, typically in Django's AppConfig.ready()
    or in settings.py.

    Args:
        cache_name: Name of the Django cache to use as the backend (default: "default")
        prefix: Global prefix for all tag names (default: "NOZ")
        global_prefix: Alias for prefix parameter (for backward compatibility)

    Example in AppConfig:
        # myapp/apps.py
        from django.apps import AppConfig

        class MyAppConfig(AppConfig):
            name = 'myapp'

            def ready(self):
                from fragmented_keys_django import configure_fragmented_keys
                configure_fragmented_keys(
                    cache_name='default',
                    prefix='MYAPP'
                )

    Example in settings.py (after Django apps are configured):
        # settings.py
        ...
        from fragmented_keys_django import configure_fragmented_keys
        configure_fragmented_keys(cache_name='default', prefix='NOZ')
    """
    from fragmented_keys import Configuration
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    # Support both parameter names for convenience
    actual_prefix = global_prefix or prefix

    handler = DjangoCacheHandler(cache_name)
    Configuration.set_default_cache_handler(handler)
    Configuration.set_global_prefix(actual_prefix)


def get_cache_handler(cache_name: str = "default"):
    """Get a configured Django cache handler for use with fragmented_keys.

    This is useful when you need a handler instance with a specific
    cache name without modifying the global configuration.

    Args:
        cache_name: Name of the Django cache to use

    Returns:
        DjangoCacheHandler instance

    Example:
        from fragmented_keys import StandardTag
        from fragmented_keys_django.config import get_cache_handler

        handler = get_cache_handler('redis_cache')
        tag = StandardTag('MyTag', 'instance', handler=handler)
    """
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    return DjangoCacheHandler(cache_name)


def reset_configuration() -> None:
    """Reset fragmented_keys configuration to defaults.

    This is primarily useful for testing to ensure a clean state
    between test cases.

    Example in tests:
        def setUp(self):
            from fragmented_keys_django.config import reset_configuration
            reset_configuration()
    """
    from fragmented_keys import Configuration

    Configuration.reset()


def set_cache_handler_globally(cache_name: str) -> None:
    """Set a new global cache handler for fragmented_keys.

    Use this when you need to change the cache backend after
    initial configuration.

    Args:
        cache_name: Name of the Django cache to use

    Example:
        from fragmented_keys_django.config import set_cache_handler_globally
        set_cache_handler_globally('memcached_cache')
    """
    from fragmented_keys import Configuration
    from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler

    handler = DjangoCacheHandler(cache_name)
    Configuration.set_default_cache_handler(handler)


def set_global_prefix(prefix: str) -> None:
    """Set the global prefix for all tag names.

    Args:
        prefix: New global prefix string

    Example:
        from fragmented_keys_django.config import set_global_prefix
        set_global_prefix('PRODUCTION')
    """
    from fragmented_keys import Configuration

    Configuration.set_global_prefix(prefix)


def get_global_prefix() -> str:
    """Get the current global prefix for tag names.

    Returns:
        Current global prefix string
    """
    from fragmented_keys import Configuration

    return Configuration.get_global_prefix()