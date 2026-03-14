"""Cache decorator using fragmented_keys for automatic invalidation."""

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
    """Decorator that fragments cache keys based on tags and parameters.

    This decorator uses fragmented_keys to create composite cache keys that
    automatically invalidate when tagged data changes. It provides a drop-in
    replacement for Django's cache_page decorator with more powerful invalidation.

    Args:
        timeout: Cache timeout in seconds (default: 3600 = 1 hour)
        tags: List of tag templates for cache invalidation. Tags can include
            parameter placeholders like 'User:{user_id}' or 'Campaign:{campaign_id}'.
        vary_on: List of parameter names to include in the cache key for variation.
        version: Optional version string for the cache key.
        key_name: Optional custom key name (defaults to function's qualified name).
        cache_name: Django cache alias to use (default: "default").

    Example:
        @tagged_cache(
            timeout=3600,
            tags=['Dashboard', 'User:{user_id}'],
            vary_on=['user_id', 'filter_type', 'start_date']
        )
        def get_dashboard_statistics(user_id: int, filter_type: str, start_date):
            # Expensive computation
            data = fetch_from_database(user_id, filter_type, start_date)
            return data

        # Cache will auto-invalidate when:
        # - User model with pk=user_id is saved/deleted (if registered with ModelTagManager)
        # - Or when ModelTagManager.invalidate_model_tag(User, user_id) is called explicitly
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
    """Resolve a parameter value from function arguments.

    Args:
        param_name: Name of the parameter to resolve
        args: Positional arguments passed to the function
        kwargs: Keyword arguments passed to the function
        func: The function being decorated

    Returns:
        The resolved parameter value

    Raises:
        KeyError: If the parameter cannot be found
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
    """Async version of tagged_cache decorator.

    Works the same as tagged_cache but wraps async functions.
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