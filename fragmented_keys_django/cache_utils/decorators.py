"""Cache decorators using fragmented_keys for automatic tag-versioned invalidation.

This module provides two decorators:

- :func:`tagged_cache` — for synchronous functions
- :func:`cached_async` — for ``async`` functions

Both follow the same internal flow:

1. **Tag resolution:** Each tag template (e.g. ``"User:{user_id}"``) is parsed
   to extract the tag name and placeholder.  The placeholder is resolved from
   the decorated function's arguments using ``inspect.signature``.

2. **Key composition:** A base key name is built from the function's qualified
   name (or a custom ``key_name``), with ``vary_on`` parameters appended.
   A ``StandardKey`` is created from this name + the resolved tags.
   ``get_key_str()`` queries the cache for each tag's current version and
   produces a deterministic composite key string.

3. **Get-or-compute:** The cache is checked for the composite key.  On hit,
   the cached value is returned without calling the function.  On miss, the
   function runs and its result is stored under the composite key.

4. **Invalidation:** When a tag version is incremented (e.g. via
   ``ModelTagManager`` signal or manual ``StandardTag.increment()``), the
   composite key resolves to a different string → automatic cache miss.
   No explicit delete needed.
"""

from __future__ import annotations

import re
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec("P")

from fragmented_keys import StandardKey, StandardTag

from fragmented_keys_django.cache_utils.tags import parse_tag_template, resolve_tag_instance


def tagged_cache(
    timeout: int = 3600,
    tags: list[str] | None = None,
    vary_on: list[str] | None = None,
    version: str | None = None,
    key_name: str | None = None,
    cache_name: str = "default",
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Decorator that caches function results using tag-versioned composite keys.

    Wraps a function with automatic cache management.  On each call, the
    decorator builds a composite cache key from the function's tags and
    arguments, checks the cache, and only calls the function on a miss.

    **Tag templates** use ``{placeholder}`` syntax to extract values from
    function arguments.  For example, ``"User:{user_id}"`` resolves
    ``user_id`` from the function's positional or keyword arguments using
    ``inspect.signature``.  Tags without placeholders (e.g. ``"Dashboard"``)
    are global — incrementing them invalidates all cached results of this
    function regardless of arguments.

    **vary_on** controls which argument combinations get their own cache
    entry.  Two calls with different ``user_id`` values produce separate
    cache keys and can be invalidated independently.

    :param timeout: Cache TTL in seconds.  Default: 3600 (1 hour).
    :param tags: List of tag template strings for cache invalidation.
        Each tag can include ``{placeholder}`` syntax for argument extraction
        (e.g. ``"User:{user_id}"``), or be a plain string for a global tag
        (e.g. ``"Dashboard"``).
    :param vary_on: List of parameter names whose values are included in the
        cache key.  If two calls pass different values for a ``vary_on``
        parameter, they get separate cache entries.
    :param version: Optional version string appended to the key name.  Changing
        this forces a cache bust (e.g. on deployment) without touching Redis.
    :param key_name: Custom base key name.  Defaults to
        ``"{func.__module__}.{func.__qualname__}"``.
    :param cache_name: Django cache alias to use for storage.  Default: ``"default"``.
    :returns: Decorator that wraps the function with caching.

    :example:

    .. code-block:: python

       @tagged_cache(
           timeout=3600,
           tags=["Dashboard", "User:{user_id}"],
           vary_on=["user_id", "filter_type"],
       )
       def get_dashboard_statistics(user_id: int, filter_type: str):
           return fetch_from_database(user_id, filter_type)

       # Cache auto-invalidates when:
       # - User model with pk=user_id is saved (if registered with ModelTagManager)
       # - ModelTagManager.invalidate_model_tag(User, user_id) is called
       # - StandardTag("Dashboard").increment() is called (global bust)
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            from django.core.cache import caches

            cache = caches[cache_name]

            # Build tags from string templates
            tag_objs = []
            for tag_template in tags or []:
                tag_name, _ = parse_tag_template(tag_template)
                instance_value = resolve_tag_instance(tag_template, args, kwargs, func)
                tag_objs.append(StandardTag(tag_name, str(instance_value)))

            # Build composite key name
            base_key_name = key_name or f"{func.__module__}.{func.__qualname__}"
            if version:
                base_key_name = f"{base_key_name}_v{version}"

            # Add varying parameters to the key
            if vary_on:
                key_parts = []
                for param in vary_on:
                    param_value = resolve_param_value(param, args, kwargs, func)
                    if param_value is not None:
                        key_parts.append(f"{param}_{param_value}")
                if key_parts:
                    base_key_name = f"{base_key_name}_{'_'.join(key_parts)}"

            # Create composite key with tags
            key = StandardKey(base_key_name, tag_objs)
            cache_key = key.get_key_str()

            # Try cache first
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            return result

        return wrapper

    return decorator


def resolve_param_value(
    param_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    func: Callable[P, Any],
) -> Any:
    """Resolve a parameter value from a function's positional or keyword arguments.

    Uses ``inspect.signature`` to map parameter names to positional indices.
    Checks ``kwargs`` first (for explicitly-passed keyword arguments), then
    falls back to positional ``args``.

    This is used by both :func:`tagged_cache` and :func:`cached_async` to
    extract ``vary_on`` parameter values from the decorated function's call.

    :param param_name: Name of the parameter to resolve (e.g. ``"user_id"``).
    :param args: Positional arguments passed to the decorated function.
    :param kwargs: Keyword arguments passed to the decorated function.
    :param func: The decorated function (used for signature introspection).
    :returns: The resolved parameter value.
    :raises KeyError: If *param_name* is not found in the function's arguments.
    """
    # Check kwargs first
    if param_name in kwargs:
        return kwargs[param_name]

    # Try to find in args using function signature
    import inspect

    sig = inspect.signature(func)
    parameters = list(sig.parameters.keys())

    try:
        param_index = parameters.index(param_name)
        if param_index < len(args):
            return args[param_index]
    except ValueError:
        pass

    raise KeyError(f"Parameter '{param_name}' not found in function arguments")


def cached_async(
    timeout: int = 3600,
    tags: list[str] | None = None,
    vary_on: list[str] | None = None,
    version: str | None = None,
    key_name: str | None = None,
    cache_name: str = "default",
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Async version of :func:`tagged_cache`.

    Identical behavior to :func:`tagged_cache`, but the inner wrapper is
    ``async def`` and ``await``\\s the decorated function.  Tag resolution
    and key composition are synchronous (string operations + cache reads);
    only the decorated function itself is awaited.

    .. note::

       Django's cache API (``cache.get`` / ``cache.set``) is called
       synchronously within the async wrapper.  This is fine because
       Django's cache backends are sync-only.  The async boundary is
       solely around your function's execution.

    :param timeout: Cache TTL in seconds.  Default: 3600.
    :param tags: Tag template strings (same syntax as :func:`tagged_cache`).
    :param vary_on: Parameter names to vary the cache key on.
    :param version: Optional version string for cache-busting.
    :param key_name: Custom base key name.
    :param cache_name: Django cache alias.  Default: ``"default"``.
    :returns: Decorator that wraps the async function with caching.

    :example:

    .. code-block:: python

       @cached_async(
           timeout=3600,
           tags=["User:{user_id}"],
           vary_on=["user_id"],
       )
       async def get_user_data(user_id: int):
           return await async_user_query(user_id)
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        import functools

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            from django.core.cache import caches

            cache = caches[cache_name]

            # Build tags from string templates
            tag_objs = []
            for tag_template in tags or []:
                tag_name, _ = parse_tag_template(tag_template)
                instance_value = resolve_tag_instance(tag_template, args, kwargs, func)
                tag_objs.append(StandardTag(tag_name, str(instance_value)))

            # Build composite key name
            base_key_name = key_name or f"{func.__module__}.{func.__qualname__}"
            if version:
                base_key_name = f"{base_key_name}_v{version}"

            if vary_on:
                key_parts = []
                for param in vary_on:
                    param_value = resolve_param_value(param, args, kwargs, func)
                    if param_value is not None:
                        key_parts.append(f"{param}_{param_value}")
                if key_parts:
                    base_key_name = f"{base_key_name}_{'_'.join(key_parts)}"

            key = StandardKey(base_key_name, tag_objs)
            cache_key = key.get_key_str()

            result = cache.get(cache_key)
            if result is not None:
                return result

            result = await func(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            return result

        return wrapper

    return decorator
