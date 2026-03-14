"""Model-based tag management with automatic invalidation via Django signals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from django.db.models.signals import post_delete, post_save

from fragmented_keys import StandardTag

if TYPE_CHECKING:
    from django.db.models import Model


class ModelTagManager:
    """Manages model-based tags and auto-invalidation via signals.

    This class provides automatic cache invalidation for Django models
    by connecting to post_save and post_delete signals. When a model
    instance is saved or deleted, all cache entries tagged with that
    model-instance are automatically invalidated.

    Example:
        # Register models for auto-invalidation
        ModelTagManager.register_model(User)
        ModelTagManager.register_model(Donation, tag_name='Donation')

        # Now use tags in your cached functions
        @tagged_cache(tags=['User:{user_id}'])
        def get_user_profile(user_id):
            return User.objects.get(pk=user_id)

        # Tag auto-increments when user is changed
        user = User.objects.get(pk=1)
        user.save()  # Cache for user 1 is now invalidated
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
        """Register a model for auto-invalidation on save/delete.

        Args:
            model: Django model class to register
            tag_name: Custom tag name (defaults to model.__name__)
            auto_connect: If True, automatically connects signals (default: True)
        """
        # Store for debugging and introspection
        cls._weak_model_classes[model.__name__] = model

        tag_name = tag_name or model.__name__
        cls._registered_models[model] = tag_name

        if auto_connect:
            cls.connect_signals(model)

    @classmethod
    def connect_signals(cls, model: Type[Model]) -> None:
        """Connect post_save and post_delete signals to a model."""
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
        """Disconnect signals from a model."""
        if model in cls._handlers:
            post_save.disconnect(cls._on_model_change, sender=model)
            post_delete.disconnect(cls._on_model_change, sender=model)
            del cls._handlers[model]

    @classmethod
    def _on_model_change(cls, sender: Type[Model], instance: Model, **kwargs: dict) -> None:
        """Signal handler that invalidates tags when model changes."""
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
        """Manually invalidate a specific model instance's tag.

        This is useful when you need to invalidate cache for a specific
        instance without triggering model signals.

        Args:
            model: Django model class or model name string
            pk: Primary key value of the instance

        Returns:
            True if tag was found and incremented, False otherwise
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
        """Get the tag name for a registered model.

        Args:
            model: Django model class

        Returns:
            Tag name if registered, None otherwise
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

        Args:
            model: Django model class

        Returns:
            True if registered, False otherwise
        """
        return model in cls._registered_models

    @classmethod
    def get_registered_models(cls) -> dict[Type[Model], str]:
        """Get all registered models and their tag names.

        Returns:
            Dictionary mapping model classes to tag names
        """
        return cls._registered_models.copy()

    @classmethod
    def unregister_model(cls, model: Type[Model]) -> None:
        """Unregister a model from auto-invalidation."""
        if model in cls._registered_models:
            cls.disconnect_signals(model)
            del cls._registered_models[model]

    @classmethod
    def clear_all(cls) -> None:
        """Clear all registered models and disconnect all signals."""
        for model in list(cls._registered_models.keys()):
            cls.unregister_model(model)