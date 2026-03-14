"""Tag factory utilities for common cache invalidation patterns."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from fragmented_keys import StandardTag

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec("P")


def model_tag(model_name: str, instance_id: str | int) -> StandardTag:
    """Create a model-instance tag for cache invalidation.

    Use this when you want to invalidate cache based on a specific
    model instance being modified.

    Args:
        model_name: Name of the model (e.g., 'User', 'Donation')
        instance_id: Primary key or unique identifier for the instance

    Returns:
        StandardTag instance configured for model-instance invalidation

    Example:
        user_tag = model_tag('User', str(user_id))
        key = StandardKey('UserProfile', [user_tag])
    """
    return StandardTag(model_name, str(instance_id))


def list_tag(list_name: str, list_id: str | int) -> StandardTag:
    """Create a tag for list/aggregation cache invalidation.

    Use this when caching paginated lists or query results that
    should be invalidated when any member of the list changes.

    Args:
        list_name: Name of the list type (e.g., 'Donations', 'Campaigns')
        list_id: Identifier for the specific list (e.g., user_id for user's donations)

    Returns:
        StandardTag instance configured for list invalidation

    Example:
        donations_tag = list_tag('Donations', str(user_id))
        key = StandardKey('UserDonations', [donations_tag])
    """
    return StandardTag(list_name, str(list_id))


def aggregate_tag(metric_name: str, filter_hash: str) -> StandardTag:
    """Create a tag for aggregated query cache invalidation.

    Use this when caching computed statistics or analytics that
    should be invalidated when underlying data changes.

    Args:
        metric_name: Name of the metric or aggregation (e.g., 'DashboardStats')
        filter_hash: Hash or representation of the query filters (e.g., 'daily_2024')

    Returns:
        StandardTag instance configured for aggregation invalidation

    Example:
        stats_tag = aggregate_tag('DashboardStats', f'daily_{user_id}')
        key = StandardKey('DashboardStatistics', [stats_tag])
    """
    return StandardTag(metric_name, str(filter_hash))


def custom_tag(tag_name: str, instance_value: str | int) -> StandardTag:
    """Create a custom tag for specialized invalidation scenarios.

    Use this for application-specific cache invalidation patterns
    that don't fit into the model, list, or aggregate categories.

    Args:
        tag_name: Name of the custom tag
        instance_value: Instance identifier for the tag

    Returns:
        StandardTag instance configured with custom values

    Example:
        weather_tag = custom_tag('Weather', f'{city}_{date}')
        key = StandardKey('WeatherData', [weather_tag])
    """
    return StandardTag(tag_name, str(instance_value))


def parse_tag_template(tag_template: str) -> tuple[str, str]:
    """Parse a tag template into name and placeholder pattern.

    Tag templates use {placeholder} syntax, e.g., 'User:{user_id}' or 'Campaign:{id}'.

    Args:
        tag_template: Tag template string with optional placeholders

    Returns:
        Tuple of (tag_name, placeholder_pattern)

    Example:
        tag_name, pattern = parse_tag_template('User:{user_id}')
        # tag_name = 'User', pattern = '{user_id}'
    """
    # Find the placeholder part
    pattern = ""
    if "{" in tag_template and "}" in tag_template:
        start = tag_template.find("{")
        end = tag_template.rfind("}") + 1
        pattern = tag_template[start:end]
        tag_name = tag_template[:start]
    else:
        tag_name = tag_template

    return tag_name.rstrip(":").strip(), pattern.strip()


def resolve_tag_instance(
    tag_template: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    func: Callable[P, Any],
) -> str:
    """Resolve a tag template placeholder to its actual value.

    Args:
        tag_template: Tag template with placeholder (e.g., 'User:{user_id}')
        args: Function positional arguments
        kwargs: Function keyword arguments
        func: The function being decorated

    Returns:
        Resolved instance value as string

    Example:
        # Given function: def get_user(user_id: int):
        # And args: (42,)
        value = resolve_tag_instance('User:{user_id}', args, {}, get_user)
        # value = '42'
    """
    _, pattern = parse_tag_template(tag_template)

    if not pattern:
        return ""

    # Extract parameter name from placeholder
    param_match = re.match(r"\{([^}]+)\}", pattern)
    if not param_match:
        return ""

    param_name = param_match.group(1)

    # Get parameter value using the same logic as in decorators
    try:
        return str(resolve_param_value(param_name, args, kwargs, func))
    except KeyError:
        return ""


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


def build_composite_key(
    base_name: str,
    tags: list[tuple[str, str | int]] | None = None,
    vary_params: list[tuple[str, Any]] | None = None,
) -> tuple[StandardTag, str]:
    """Build a composite cache key with tags and varying parameters.

    This helper function creates both the tags and the base key name
    for use with StandardKey.

    Args:
        base_name: Base name for the cache key
        tags: List of (tag_name, instance_id) tuples
        vary_params: List of (param_name, param_value) tuples for key variation

    Returns:
        Tuple of (list of StandardTag, string key name)

    Example:
        tags_list, key_name = build_composite_key(
            'UserProfile',
            tags=[('User', '42')],
            vary_params=[('include_history', 'true')]
        )
        # Then use:
        # key = StandardKey(key_name, tags_list)
    """
    tag_objs = []
    if tags:
        for tag_name, instance_id in tags:
            tag_objs.append(StandardTag(tag_name, str(instance_id)))

    key_name = base_name
    if vary_params:
        key_parts = []
        for param_name, param_value in vary_params:
            key_parts.append(f"{param_name}_{param_value}")
        if key_parts:
            key_name = f"{base_name}_{'_'.join(key_parts)}"

    # Return just the tag list and key name
    # StandardKey will be created by the caller
    return tag_objs, key_name