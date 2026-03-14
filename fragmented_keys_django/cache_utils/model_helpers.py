"""Model-based tag management with automatic invalidation via Django signals.

This module provides :class:`ModelTagManager`, which connects Django's ORM
signals to the ``fragmented_keys`` tag versioning system.  When a registered
model instance is saved or deleted, its corresponding tag version is
automatically incremented — no manual cache management needed.

**Signal flow:**

1. You call ``ModelTagManager.register_model(User)`` in ``AppConfig.ready()``.
2. This connects ``post_save`` and ``post_delete`` signals for ``User``
   with ``weak=False`` (so the handler isn't garbage collected).
3. When ``User(pk=42).save()`` fires, Django emits ``post_save``.
4. ``_on_model_change`` looks up ``User`` in ``_registered_models`` → finds
   the tag name ``"User"``.
5. Creates ``StandardTag("User", "42")`` and calls ``.increment()``.
6. The tag version is bumped in the cache.  Any composite key embedding
   ``User:42`` now resolves to a different string → automatic cache miss.

**Scope is per-instance, not per-model.**  Saving ``User(pk=42)`` only
increments ``User:42``.  All other users' cached data is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from django.db.models.signals import post_delete, post_save

from fragmented_keys import StandardTag

if TYPE_CHECKING:
    from django.db.models import Model


class ModelTagManager:
    """Manages model-based tags and auto-invalidation via Django signals.

    A class-level registry that maps Django model classes to tag names and
    connects ORM signals for automatic tag version incrementing.

    All methods are ``@classmethod`` — there is no need to instantiate
    ``ModelTagManager``.  The registry (``_registered_models``) and signal
    handlers (``_handlers``) are shared across the entire process.

    **Typical setup** (in ``AppConfig.ready()``):

    .. code-block:: python

       from fragmented_keys_django import ModelTagManager
       from django.contrib.auth.models import User
       from myapp.models import Donation

       ModelTagManager.register_model(User)                      # tag: User:{pk}
       ModelTagManager.register_model(Donation, tag_name="Don")   # tag: Don:{pk}

    **How invalidation works:**

    After registration, ``user.save()`` triggers ``post_save`` →
    ``_on_model_change`` → ``StandardTag("User", str(user.pk)).increment()``.
    Any cache key composed with ``User:{pk}`` now resolves to a different
    string → cache miss → recomputation on next access.

    .. warning::

       The ``tag_name`` used at registration must match the tag names in your
       ``@tagged_cache`` decorators and ``*_with_tags`` calls.  If you register
       ``Donation`` with ``tag_name="Don"``, your decorators must use
       ``tags=["Don:{donation_id}"]``, not ``"Donation:{donation_id}"``.
    """

    _registered_models: dict[Type[Model], str] = {}
    _handlers: dict[Type[Model], frozenset] = {}
    _weak_model_classes: dict = {}

    @classmethod
    def register_model(
        cls,
        model: Type[Model],
        tag_name: str | None = None,
        auto_connect: bool = True,
    ) -> None:
        """Register a model for automatic tag invalidation on save/delete.

        Stores the model → tag name mapping and (by default) connects
        ``post_save`` and ``post_delete`` signal handlers.

        :param model: Django model class to register.
        :param tag_name: Tag name to use for this model.  Defaults to
            ``model.__name__`` (e.g. ``"User"``).  Must match the tag names
            used in ``@tagged_cache`` decorators.
        :param auto_connect: If ``True`` (default), immediately connects
            signal handlers.  Set to ``False`` if you want to register
            the mapping without connecting signals (e.g. for testing).
        """
        # Store for debugging and introspection
        cls._weak_model_classes[model.__name__] = model

        tag_name = tag_name or model.__name__
        cls._registered_models[model] = tag_name

        if auto_connect:
            cls.connect_signals(model)

    @classmethod
    def connect_signals(cls, model: Type[Model]) -> None:
        """Connect ``post_save`` and ``post_delete`` signals for a model.

        Disconnects any existing handlers first to prevent duplicate
        registrations (safe to call multiple times, e.g. if ``AppConfig.ready()``
        runs twice during testing).

        Signal handlers are connected with ``weak=False`` to ensure they
        persist for the lifetime of the process.

        :param model: Django model class to connect signals for.
        """
        # Disconnect existing handlers to avoid duplicates
        cls.disconnect_signals(model)

        # Connect new handlers with weak=False to ensure they persist
        handler_ids = frozenset([
            post_save.connect(cls._on_model_change, sender=model, weak=False),
            post_delete.connect(cls._on_model_change, sender=model, weak=False),
        ])
        cls._handlers[model] = handler_ids

    @classmethod
    def disconnect_signals(cls, model: Type[Model]) -> None:
        """Disconnect signal handlers for a model.

        Safe to call even if no handlers are connected (no-op in that case).

        :param model: Django model class to disconnect signals for.
        """
        if model in cls._handlers:
            post_save.disconnect(cls._on_model_change, sender=model)
            post_delete.disconnect(cls._on_model_change, sender=model)
            del cls._handlers[model]

    @classmethod
    def _on_model_change(cls, sender: Type[Model], instance: Model, **kwargs: dict) -> None:
        """Signal handler that increments a tag when a model instance changes.

        Connected to ``post_save`` and ``post_delete`` for registered models.
        Looks up the tag name for the sender model, then calls
        ``StandardTag(tag_name, str(instance.pk)).increment()``.

        Errors are silently caught to prevent signal failures from breaking
        normal ORM operations.  This means a failed Redis connection won't
        cause ``model.save()`` to raise — the cache simply won't be invalidated
        until Redis recovers.

        :param sender: The model class that sent the signal.
        :param instance: The model instance that was saved/deleted.
        :param kwargs: Additional signal kwargs (``created``, ``raw``, etc.).
        """
        # Only invalidate if the model is registered
        if sender not in cls._registered_models:
            return

        tag_name = cls._registered_models[sender]

        try:
            # Get the primary key - might fail for unsaved instances
            pk_value = instance.pk
            if pk_value is None:
                return

            # Increment the tag to invalidate all dependent cache keys
            tag = StandardTag(tag_name, str(pk_value))
            tag.increment()
        except Exception:
            # Silently handle errors - we don't want signal failures to break normal operations
            pass

    @classmethod
    def invalidate_model_tag(cls, model: Type[Model] | str, pk: int | str) -> bool:
        """Manually increment a tag for a specific model instance.

        Use this for changes that bypass Django's ORM signals — bulk SQL
        updates, raw queries, external webhooks, management commands, or
        Celery tasks that modify data without calling ``model.save()``.

        This does the same thing the ``post_save`` signal handler does:
        increments ``StandardTag(tag_name, str(pk))``.

        :param model: Django model class, or model name as a string
            (matched against ``model.__name__`` of registered models).
        :param pk: Primary key of the instance to invalidate.
        :returns: ``True`` if the tag was found and incremented,
            ``False`` if the model is not registered or an error occurred.

        :example:

        .. code-block:: python

           # After a bulk SQL update that bypasses .save()
           cursor.execute("UPDATE auth_user SET is_active=False WHERE ...")
           for user_id in affected_ids:
               ModelTagManager.invalidate_model_tag(User, user_id)
        """
        tag_name: str

        if isinstance(model, str):
            # Look up by model name
            model_name = model
            # Check registered models
            tag_name = None
            for m, tn in cls._registered_models.items():
                if m.__name__ == model_name:
                    tag_name = tn
                    break
            if tag_name is None:
                return False
        else:
            if model not in cls._registered_models:
                return False
            tag_name = cls._registered_models[model]

        try:
            tag = StandardTag(tag_name, str(pk))
            tag.increment()
            return True
        except Exception:
            return False

    @classmethod
    def get_tag_name_for_model(cls, model: Type[Model]) -> str | None:
        """Get the registered tag name for a model.

        Tries a direct dict lookup first, then falls back to
        ``django.apps.apps.get_model()`` for ``"app_label.ModelName"``
        style lookups.

        :param model: Django model class.
        :returns: Tag name string if registered, ``None`` otherwise.
        """
        from django.apps import apps

        # Try direct lookup first
        if model in cls._registered_models:
            return cls._registered_models[model]

        # Try lookup by app_label.model_name
        try:
            model_class = apps.get_model(model)
            if model_class in cls._registered_models:
                return cls._registered_models[model_class]
        except Exception:
            pass

        return None

    @classmethod
    def is_registered(cls, model: Type[Model]) -> bool:
        """Check if a model is registered for auto-invalidation.

        :param model: Django model class.
        :returns: ``True`` if registered, ``False`` otherwise.
        """
        return model in cls._registered_models

    @classmethod
    def get_registered_models(cls) -> dict[Type[Model], str]:
        """Return all registered models and their tag names.

        Returns a *copy* of the internal registry so callers cannot
        accidentally mutate it.

        :returns: Dict mapping model classes to their tag name strings.
        """
        return cls._registered_models.copy()

    @classmethod
    def unregister_model(cls, model: Type[Model]) -> None:
        """Unregister a model, disconnecting its signal handlers.

        After this call, ``model.save()`` will no longer increment any
        tags.  Existing cached entries tagged with this model are not
        deleted — they expire via their original TTL.

        :param model: Django model class to unregister.
        """
        if model in cls._registered_models:
            cls.disconnect_signals(model)
            del cls._registered_models[model]

    @classmethod
    def clear_all(cls) -> None:
        """Unregister all models and disconnect all signal handlers.

        Useful in test teardowns to ensure signal handlers from one test
        don't leak into another.
        """
        for model in list(cls._registered_models.keys()):
            cls.unregister_model(model)
