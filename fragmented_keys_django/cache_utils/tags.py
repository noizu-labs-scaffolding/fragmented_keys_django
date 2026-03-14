"""Tag factory utilities and template resolution for cache invalidation patterns.

This module provides:

**Tag factories** — semantic aliases for ``StandardTag`` construction:

- :func:`model_tag` — for caches tied to a single model instance
- :func:`list_tag` — for caches of collections/queries scoped to an owner
- :func:`aggregate_tag` — for computed statistics or rollups
- :func:`custom_tag` — for application-specific patterns

All four are behaviorally identical (they all call ``StandardTag(name, str(id))``).
The different names communicate intent to future readers.

**Template resolution** — used internally by the ``@tagged_cache`` decorator:

- :func:`parse_tag_template` — splits ``"User:{user_id}"`` into name + placeholder
- :func:`resolve_tag_instance` — resolves the placeholder from function arguments
- :func:`resolve_param_value` — extracts a named parameter from args/kwargs
- :func:`build_composite_key` — convenience for building tags + key name together
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from fragmented_keys import StandardTag

if TYPE_CHECKING:
    from typing import ParamSpec

    P = ParamSpec("P")


def model_tag(model_name: str, instance_id: str | int) -> StandardTag:
    """Create a tag for a specific model instance.

    Use this when a cache should be invalidated when a particular model
    instance is modified.  Pairs naturally with
    :meth:`~fragmented_keys_django.cache_utils.model_helpers.ModelTagManager.register_model`
    — when the model is saved, the signal handler increments the same tag.

    Internally, this is just ``StandardTag(model_name, str(instance_id))``.

    :param model_name: Tag name, typically matching the model's class name
        (e.g. ``"User"``).  Must match the ``tag_name`` used in
        ``ModelTagManager.register_model()`` for auto-invalidation to work.
    :param instance_id: Primary key or unique identifier for the instance.
    :returns: A :class:`StandardTag` instance.

    :example:

    .. code-block:: python

       user_tag = model_tag("User", str(user_id))
       key = StandardKey("UserProfile", [user_tag])
       cache_key = key.get_key_str()
    """
    return StandardTag(model_name, str(instance_id))


def list_tag(list_name: str, list_id: str | int) -> StandardTag:
    """Create a tag for a collection or query result scoped to an owner.

    Use this when caching paginated lists, filtered querysets, or any
    collection that should be invalidated when its membership changes.

    Internally, this is just ``StandardTag(list_name, str(list_id))``.

    .. note::

       You must arrange for the tag to be incremented when the list changes.
       Options: register the parent model with ``ModelTagManager``, or call
       ``StandardTag(list_name, str(list_id)).increment()`` manually when
       items are added/removed.

    :param list_name: Tag name for the list type (e.g. ``"Donations"``).
    :param list_id: Identifier scoping the list (e.g. ``user_id`` for
        "this user's donations").
    :returns: A :class:`StandardTag` instance.

    :example:

    .. code-block:: python

       donations_tag = list_tag("Donations", str(user_id))
       key = StandardKey("UserDonations", [donations_tag])
    """
    return StandardTag(list_name, str(list_id))


def aggregate_tag(metric_name: str, filter_hash: str) -> StandardTag:
    """Create a tag for computed statistics or rollup caches.

    Use this when caching aggregated queries, analytics dashboards, or
    any computed result that depends on a combination of filters.

    Internally, this is just ``StandardTag(metric_name, str(filter_hash))``.

    :param metric_name: Tag name for the metric (e.g. ``"DashboardStats"``).
    :param filter_hash: String representing the query filters
        (e.g. ``f"daily_{user_id}"``).
    :returns: A :class:`StandardTag` instance.

    :example:

    .. code-block:: python

       stats_tag = aggregate_tag("DashboardStats", f"daily_{user_id}")
       key = StandardKey("DashboardStatistics", [stats_tag])
    """
    return StandardTag(metric_name, str(filter_hash))


def custom_tag(tag_name: str, instance_value: str | int) -> StandardTag:
    """Create a tag for application-specific invalidation patterns.

    Use this for patterns that don't fit the ``model``, ``list``, or
    ``aggregate`` categories — e.g. weather data, feature flags,
    configuration caches.

    Internally, this is just ``StandardTag(tag_name, str(instance_value))``.

    :param tag_name: Tag name.
    :param instance_value: Instance identifier.
    :returns: A :class:`StandardTag` instance.

    :example:

    .. code-block:: python

       weather_tag = custom_tag("Weather", f"{city}_{date}")
       key = StandardKey("WeatherData", [weather_tag])
    """
    return StandardTag(tag_name, str(instance_value))


def parse_tag_template(tag_template: str) -> tuple[str, str]:
    """Parse a tag template string into its name and placeholder components.

    Tag templates use ``{placeholder}`` syntax.  For example,
    ``"User:{user_id}"`` is parsed into tag name ``"User"`` and placeholder
    ``"{user_id}"``.  Templates without placeholders (e.g. ``"Dashboard"``)
    return an empty placeholder string.

    The tag name is everything before the first ``{``, with trailing colons
    and whitespace stripped.  The placeholder is everything from the first
    ``{`` to the last ``}`` (inclusive).

    :param tag_template: Tag template string (e.g. ``"User:{user_id}"``
        or ``"Dashboard"``).
    :returns: Tuple of ``(tag_name, placeholder_pattern)``.  The placeholder
        is an empty string if the template has no ``{...}`` syntax.

    :example:

    .. code-block:: python

       parse_tag_template("User:{user_id}")   # ("User", "{user_id}")
       parse_tag_template("Dashboard")         # ("Dashboard", "")
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
    """Resolve a tag template's placeholder to its actual value from function arguments.

    Extracts the parameter name from the ``{placeholder}`` in the tag template,
    then looks it up in the function's positional or keyword arguments using
    :func:`resolve_param_value`.

    If the template has no placeholder, returns an empty string (global tag).

    .. note::

       Only the *first* ``{param}`` in the template is resolved.  Templates
       like ``"User:{user_id}:Role:{role_id}"`` will only resolve ``user_id``.
       Use separate tags for multi-dimension dependencies.

    :param tag_template: Tag template string (e.g. ``"User:{user_id}"``).
    :param args: Positional arguments passed to the decorated function.
    :param kwargs: Keyword arguments passed to the decorated function.
    :param func: The decorated function (used for signature introspection).
    :returns: Resolved instance value as a string, or ``""`` for global tags
        or unresolvable placeholders.

    :example:

    .. code-block:: python

       # Given: def get_user(user_id: int): ...
       # Called with: get_user(42)
       resolve_tag_instance("User:{user_id}", (42,), {}, get_user)  # "42"
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
    """Resolve a named parameter from a function's positional or keyword arguments.

    Checks ``kwargs`` first (for explicitly-passed keyword arguments), then
    uses ``inspect.signature`` to find the parameter's positional index in
    ``args``.

    :param param_name: Name of the parameter to resolve.
    :param args: Positional arguments passed to the function.
    :param kwargs: Keyword arguments passed to the function.
    :param func: The function (used for signature introspection via
        ``inspect.signature``).
    :returns: The resolved parameter value (any type).
    :raises KeyError: If *param_name* is not found in either ``args`` or ``kwargs``.
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
    """Build tag objects and a composite key name in one call.

    Convenience function that combines tag creation (from tuples) and key
    name construction (from base name + vary parameters).  This is the same
    logic that :func:`tagged_cache` uses internally, exposed as a standalone
    function for use in services, management commands, or anywhere a
    decorator doesn't fit.

    :param base_name: Base name for the cache key (e.g. ``"UserProfile"``).
    :param tags: List of ``(tag_name, instance_id)`` tuples.  Each is
        converted to a ``StandardTag``.
    :param vary_params: List of ``(param_name, param_value)`` tuples.  Each
        is appended to the key name as ``"{name}_{value}"``.
    :returns: Tuple of ``(list_of_StandardTags, composed_key_name)``.
        Create a ``StandardKey(key_name, tag_objs)`` with the result.

    :example:

    .. code-block:: python

       tag_objs, key_name = build_composite_key(
           "UserProfile",
           tags=[("User", "42")],
           vary_params=[("include_history", "true")],
       )
       # tag_objs = [StandardTag("User", "42")]
       # key_name = "UserProfile_include_history_true"

       key = StandardKey(key_name, tag_objs)
       cache_key = key.get_key_str()
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
