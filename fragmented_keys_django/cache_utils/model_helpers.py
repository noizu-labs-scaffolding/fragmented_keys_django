"""Model-based tag management with automatic invalidation via Django signals.

This module provides :class:`ModelTagManager`, which connects Django's ORM
signals to the ``fragmented_keys`` tag versioning system.  When a registered
model instance is saved or deleted, its corresponding tag version is
automatically incremented — no manual cache management needed.

**Signal flow (v0.2.0+):**

1. You call ``ModelTagManager.register_model(User, tag_name="user")`` in
   ``AppConfig.ready()``, optionally with lifecycle hooks.
2. This connects separate ``post_save`` and ``post_delete`` signal handlers.
3. When ``User(pk=42).save()`` fires, Django emits ``post_save`` with
   ``created=True/False`` and ``update_fields``.
4. ``_on_model_save`` dispatches to the ``on_create`` or ``on_update`` callback
   (if provided), or falls back to incrementing ``StandardTag(tag_name, str(pk))``.
5. When ``User(pk=42).delete()`` fires, ``_on_model_delete`` dispatches to the
   ``on_delete`` callback or falls back to the same default.

**Lifecycle hooks** enable scoped invalidation — e.g., when a review is saved,
also bump the parent organization's review-list tag::

    def on_review_save(sender, instance):
        return [
            ("review", str(instance.pk)),
            ("review", f"org:{instance.organization_id}"),
        ]

    ModelTagManager.register_model(Review, tag_name="review", on_create=on_review_save)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Type

from django.db.models.signals import post_delete, post_save
from opentelemetry import trace

from fragmented_keys import StandardTag

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("gnp-backend.cache")

if TYPE_CHECKING:
    from django.db.models import Model

LifecycleCallback = Callable[..., list[tuple[str, str]]]


class ModelTagManager:
    """Manages model-based tags and auto-invalidation via Django signals.

    A class-level registry that maps Django model classes to tag configurations
    and connects ORM signals for automatic tag version incrementing.

    All methods are ``@classmethod`` — there is no need to instantiate
    ``ModelTagManager``.  The registry and signal handlers are shared across
    the entire process.

    **Typical setup** (in ``AppConfig.ready()``):

    .. code-block:: python

       from fragmented_keys_django import ModelTagManager

       # Simple registration — increments tag_name:pk on any change
       ModelTagManager.register_model(User, tag_name="user")

       # With lifecycle hooks — custom invalidation per signal type
       ModelTagManager.register_model(Review, tag_name="review",
           on_create=lambda s, i: [("review", str(i.pk)), ("review", f"org:{i.organization_id}")],
           on_update=lambda s, i, uf: [("review", str(i.pk)), ("review", f"org:{i.organization_id}")],
           on_delete=lambda s, i: [("review", str(i.pk)), ("review", f"org:{i.organization_id}")],
       )

    # @todo @pri-2 @keith - Lifecycle hook expansion:
    # 1. Add on_fetch/on_get hooks that fire on cache reads (useful for tracking access patterns)
    # 2. Add pre_save/pre_delete hooks (currently only post_save/post_delete are connected)
    # 3. Consider on_list hook for queryset-level operations (e.g., .filter().values_list())
    # 4. CacheAwareManager already handles bulk write ops - extend to support read-side hooks
    """

    _registered_models: dict[Type[Model], dict[str, Any]] = {}
    _handlers: dict[Type[Model], frozenset] = {}
    _weak_model_classes: dict = {}

    @classmethod
    def register_model(
        cls,
        model: Type[Model],
        tag_name: str | None = None,
        auto_connect: bool = True,
        on_create: LifecycleCallback | None = None,
        on_update: LifecycleCallback | None = None,
        on_delete: LifecycleCallback | None = None,
    ) -> None:
        """Register a model for automatic tag invalidation on save/delete.

        :param model: Django model class to register.
        :param tag_name: Tag name to use for this model.  Defaults to
            ``model.__name__``.
        :param auto_connect: If ``True`` (default), immediately connects
            signal handlers.
        :param on_create: ``(sender, instance) -> [(tag_name, instance_id), ...]``
            Called on ``post_save`` when ``created=True``.  Returns list of tags
            to increment.  If ``None``, defaults to ``[(tag_name, str(pk))]``.
        :param on_update: ``(sender, instance, update_fields) -> [(tag_name, instance_id), ...]``
            Called on ``post_save`` when ``created=False``.  Receives
            ``update_fields`` (set or None).  If ``None``, defaults to
            ``[(tag_name, str(pk))]``.
        :param on_delete: ``(sender, instance) -> [(tag_name, instance_id), ...]``
            Called on ``post_delete``.  If ``None``, defaults to
            ``[(tag_name, str(pk))]``.
        """
        cls._weak_model_classes[model.__name__] = model

        resolved_tag_name = tag_name or model.__name__
        cls._registered_models[model] = {
            "tag_name": resolved_tag_name,
            "on_create": on_create,
            "on_update": on_update,
            "on_delete": on_delete,
        }

        if auto_connect:
            cls.connect_signals(model)

    @classmethod
    def connect_signals(cls, model: Type[Model]) -> None:
        """Connect ``post_save`` and ``post_delete`` signals for a model.

        Uses separate handlers for save vs delete so lifecycle hooks
        receive the correct signal context.
        """
        cls.disconnect_signals(model)

        handler_ids = frozenset([
            post_save.connect(cls._on_model_save, sender=model, weak=False),
            post_delete.connect(cls._on_model_delete, sender=model, weak=False),
        ])
        cls._handlers[model] = handler_ids

    @classmethod
    def disconnect_signals(cls, model: Type[Model]) -> None:
        """Disconnect signal handlers for a model."""
        if model in cls._handlers:
            post_save.disconnect(cls._on_model_save, sender=model)
            post_delete.disconnect(cls._on_model_delete, sender=model)
            del cls._handlers[model]

    @classmethod
    def _increment_tags(cls, tags_to_bump: list[tuple[str, str]]) -> None:
        """Increment all tags in the list, plus global ``*`` tags.

        For each unique ``tag_name`` in the list, also bumps
        ``StandardTag(tag_name, "*")`` so that 1-tuple cache keys
        (which resolve to the global ``*`` instance) are invalidated.

        This is a temporary measure while views migrate from 1-tuples
        to 2-tuples.  Errors are logged and recorded on the active span.
        """
        with tracer.start_as_current_span("cache.invalidation") as span:
            span.set_attribute("cache.tags.count", len(tags_to_bump))
            tag_names = list(set(t[0] for t in tags_to_bump))[:10]
            span.set_attribute("cache.tags.names", ",".join(tag_names))

            bumped = 0
            errors = 0
            global_tags_bumped: set[str] = set()
            for tag_name, instance_id in tags_to_bump:
                try:
                    tag = StandardTag(tag_name, str(instance_id))
                    tag.increment()
                    bumped += 1
                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "Tag increment failed",
                        extra={"tag": tag_name, "instance": instance_id},
                        exc_info=True,
                    )
                    span.record_exception(exc)

                # Bump the global * tag for this tag_name (once per name).
                # Skip if the instance_id is already "*" to avoid double-bump.
                if instance_id != "*" and tag_name not in global_tags_bumped:
                    global_tags_bumped.add(tag_name)
                    try:
                        global_tag = StandardTag(tag_name, "*")
                        global_tag.increment()
                        bumped += 1
                    except Exception as exc:
                        errors += 1
                        logger.warning(
                            "Tag increment failed",
                            extra={"tag": tag_name, "instance": "*"},
                            exc_info=True,
                        )
                        span.record_exception(exc)

            span.set_attribute("cache.tags.bumped", bumped)
            span.set_attribute("cache.tags.errors", errors)

    @classmethod
    def _on_model_save(
        cls, sender: Type[Model], instance: Model, **kwargs: Any
    ) -> None:
        """Signal handler for ``post_save``. Dispatches to on_create or on_update."""
        if sender not in cls._registered_models:
            return

        config = cls._registered_models[sender]
        tag_name = config["tag_name"]

        try:
            pk_value = instance.pk
            if pk_value is None:
                return

            created = kwargs.get("created", False)
            update_fields = kwargs.get("update_fields")

            if created and config["on_create"] is not None:
                tags_to_bump = config["on_create"](sender, instance)
            elif not created and config["on_update"] is not None:
                tags_to_bump = config["on_update"](sender, instance, update_fields)
            else:
                tags_to_bump = [(tag_name, str(pk_value))]

            cls._increment_tags(tags_to_bump)
        except Exception as exc:
            logger.warning(
                "Cache invalidation failed on model change",
                extra={"model": sender.__name__, "pk": str(pk_value)},
                exc_info=True,
            )

    @classmethod
    def _on_model_delete(
        cls, sender: Type[Model], instance: Model, **kwargs: Any
    ) -> None:
        """Signal handler for ``post_delete``. Dispatches to on_delete."""
        if sender not in cls._registered_models:
            return

        config = cls._registered_models[sender]
        tag_name = config["tag_name"]

        try:
            pk_value = instance.pk
            if pk_value is None:
                return

            if config["on_delete"] is not None:
                tags_to_bump = config["on_delete"](sender, instance)
            else:
                tags_to_bump = [(tag_name, str(pk_value))]

            cls._increment_tags(tags_to_bump)
        except Exception as exc:
            logger.warning(
                "Cache invalidation failed on model change",
                extra={"model": sender.__name__, "pk": str(pk_value)},
                exc_info=True,
            )

    @classmethod
    def _fire_lifecycle(
        cls,
        signal_type: str,
        model: Type[Model],
        instance: Any,
        update_fields: list[str] | set[str] | None = None,
    ) -> None:
        """Execute the appropriate lifecycle callback and increment returned tags.

        Intended for use by :class:`CacheAwareManager` and
        :class:`CacheAwareQuerySet` to fire invalidation after bulk operations
        that bypass Django signals.

        :param signal_type: One of ``"create"``, ``"update"``, ``"delete"``.
        :param model: The Django model class.
        :param instance: The model instance (or a ``_FakePKInstance`` with ``.pk``).
        :param update_fields: For ``"update"`` signals, the list of changed fields.
        """
        if model not in cls._registered_models:
            return

        config = cls._registered_models[model]
        tag_name = config["tag_name"]

        try:
            pk_value = instance.pk
            if pk_value is None:
                return

            if signal_type == "create" and config["on_create"] is not None:
                tags_to_bump = config["on_create"](model, instance)
            elif signal_type == "update" and config["on_update"] is not None:
                tags_to_bump = config["on_update"](model, instance, update_fields)
            elif signal_type == "delete" and config["on_delete"] is not None:
                tags_to_bump = config["on_delete"](model, instance)
            else:
                tags_to_bump = [(tag_name, str(pk_value))]

            cls._increment_tags(tags_to_bump)
        except Exception as exc:
            logger.warning(
                "Lifecycle callback failed",
                extra={"model": model.__name__ if hasattr(model, '__name__') else str(model),
                       "signal_type": signal_type},
                exc_info=True,
            )
            # @todo @pri-2 @keith - trace tracking and logging to signoz with json format needed
            # For now errors are logged to stdout. Future: emit structured JSON logs that SigNoz
            # can index, and add span.record_exception() for trace correlation.

    @classmethod
    def invalidate_scope(cls, tag_name: str, scope_id: str) -> bool:
        """Bump a scoped tag version.

        Use this for scoped invalidation patterns where the tag instance
        represents a scope rather than a model PK.

        :param tag_name: Tag name (e.g. ``"review"``).
        :param scope_id: Scope identifier (e.g. ``"org:42"``).
        :returns: ``True`` on success, ``False`` on error.

        :example:

        .. code-block:: python

           # After bulk-creating reviews for org 42
           ModelTagManager.invalidate_scope("review", "org:42")
        """
        try:
            cls._increment_tags([(tag_name, str(scope_id))])
            return True
        except Exception:
            return False

    @classmethod
    def invalidate_bulk(
        cls,
        model_or_tag: Type[Model] | str,
        pks: list[int | str] | None = None,
        scopes: list[str] | None = None,
    ) -> int:
        """Invalidate tags after a bulk operation.

        Bumps instance tags for each pk (if provided) and scope tags
        (if provided).  Use after ``bulk_create``, ``bulk_update``,
        ``.filter().delete()``, or raw SQL that bypasses Django signals.

        :param model_or_tag: Django model class or tag name string.
        :param pks: List of primary keys whose instance tags should be bumped.
        :param scopes: List of scope identifiers to bump (e.g. ``["org:42"]``).
        :returns: Number of tags successfully incremented.

        :example:

        .. code-block:: python

           # After: OrgCategory.objects.filter(org_id=42).delete()
           ModelTagManager.invalidate_bulk(
               OrgCategory, pks=[1, 2, 3], scopes=["org:42"]
           )
        """
        tag_name = cls._resolve_tag_name(model_or_tag)
        if tag_name is None:
            return 0

        tags_to_bump: list[tuple[str, str]] = []
        if pks:
            for pk in pks:
                tags_to_bump.append((tag_name, str(pk)))
        if scopes:
            for scope_id in scopes:
                tags_to_bump.append((tag_name, str(scope_id)))

        if not tags_to_bump:
            return 0

        cls._increment_tags(tags_to_bump)
        return len(tags_to_bump)

    @classmethod
    def invalidate_model_tag(cls, model: Type[Model] | str, pk: int | str) -> bool:
        """Manually increment a tag for a specific model instance.

        Use this for changes that bypass Django's ORM signals.

        :param model: Django model class, or model name as a string.
        :param pk: Primary key of the instance to invalidate.
        :returns: ``True`` if the tag was found and incremented.
        """
        tag_name = cls._resolve_tag_name(model)
        if tag_name is None:
            return False

        try:
            cls._increment_tags([(tag_name, str(pk))])
            return True
        except Exception:
            return False

    @classmethod
    def _resolve_tag_name(cls, model_or_tag: Type[Model] | str) -> str | None:
        """Resolve a model class or string to a tag name."""
        if isinstance(model_or_tag, str):
            for m, config in cls._registered_models.items():
                if m.__name__ == model_or_tag or config["tag_name"] == model_or_tag:
                    return config["tag_name"]
            return None
        else:
            config = cls._registered_models.get(model_or_tag)
            return config["tag_name"] if config else None

    @classmethod
    def get_tag_name_for_model(cls, model: Type[Model]) -> str | None:
        """Get the registered tag name for a model."""
        from django.apps import apps

        config = cls._registered_models.get(model)
        if config:
            return config["tag_name"]

        try:
            model_class = apps.get_model(model)
            config = cls._registered_models.get(model_class)
            if config:
                return config["tag_name"]
        except Exception:
            pass

        return None

    @classmethod
    def is_registered(cls, model: Type[Model]) -> bool:
        """Check if a model is registered for auto-invalidation."""
        return model in cls._registered_models

    @classmethod
    def get_registered_models(cls) -> dict[Type[Model], str]:
        """Return all registered models and their tag names.

        Returns a dict mapping model classes to tag name strings (backward
        compatible format — only the tag_name, not the full config).
        """
        return {m: c["tag_name"] for m, c in cls._registered_models.items()}

    @classmethod
    def get_registered_config(cls, model: Type[Model]) -> dict[str, Any] | None:
        """Return the full registration config for a model, or None."""
        return cls._registered_models.get(model)

    @classmethod
    def unregister_model(cls, model: Type[Model]) -> None:
        """Unregister a model, disconnecting its signal handlers."""
        if model in cls._registered_models:
            cls.disconnect_signals(model)
            del cls._registered_models[model]

    @classmethod
    def clear_all(cls) -> None:
        """Unregister all models and disconnect all signal handlers."""
        for model in list(cls._registered_models.keys()):
            cls.unregister_model(model)
