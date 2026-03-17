"""Tests for ModelTagManager."""

from unittest.mock import MagicMock, patch, ANY
from django.db.models.signals import post_save, post_delete

import pytest

from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager


class TestModelTagManager:
    """Tests for ModelTagManager auto-invalidation system."""

    def test_register_model(self, mock_model_class):
        """Test registering a model for auto-invalidation."""
        ModelTagManager.register_model(mock_model_class)

        assert ModelTagManager.is_registered(mock_model_class)
        assert ModelTagManager.get_tag_name_for_model(mock_model_class) == "MockModel"

    def test_register_model_custom_name(self, mock_model_class):
        """Test registering a model with custom tag name."""
        ModelTagManager.register_model(mock_model_class, tag_name="CustomTag")

        assert ModelTagManager.get_tag_name_for_model(mock_model_class) == "CustomTag"

    def test_register_model_no_auto_connect(self, mock_model_class):
        """Test registering a model without auto-connecting signals."""
        with patch.object(ModelTagManager, 'connect_signals') as mock_connect:
            ModelTagManager.register_model(mock_model_class, auto_connect=False)
            mock_connect.assert_not_called()

    def test_unregister_model(self, mock_model_class):
        """Test unregistering a model."""
        ModelTagManager.register_model(mock_model_class)
        assert ModelTagManager.is_registered(mock_model_class)

        ModelTagManager.unregister_model(mock_model_class)
        assert not ModelTagManager.is_registered(mock_model_class)

    def test_is_registered(self, mock_model_class):
        """Test checking if a model is registered."""
        assert not ModelTagManager.is_registered(mock_model_class)

        ModelTagManager.register_model(mock_model_class)
        assert ModelTagManager.is_registered(mock_model_class)

    def test_get_registered_models(self, mock_model_class):
        """Test getting all registered models."""
        ModelTagManager.register_model(mock_model_class)

        registered = ModelTagManager.get_registered_models()

        assert mock_model_class in registered
        assert registered[mock_model_class] == "MockModel"

    def test_clear_all(self, mock_model_class):
        """Test clearing all registered models."""
        ModelTagManager.register_model(mock_model_class)
        assert len(ModelTagManager.get_registered_models()) > 0

        ModelTagManager.clear_all()
        assert len(ModelTagManager.get_registered_models()) == 0

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_by_class(self, mock_standard_tag, mock_model_class):
        """Test manual invalidation by model class."""
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_standard_tag.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)

        assert result is True
        mock_tag.increment.assert_called_once()

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_by_name(self, mock_standard_tag, mock_model_class):
        """Test manual invalidation by model name."""
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_standard_tag.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag("MockModel", 42)

        assert result is True
        mock_tag.increment.assert_called_once()

    def test_invalidate_model_tag_not_registered(self, mock_model_class):
        """Test manual invalidation of unregistered model."""
        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)
        assert result is False

    def test_invalidate_model_tag_by_wrong_name(self, mock_model_class):
        """Test manual invalidation with wrong model name."""
        ModelTagManager.register_model(mock_model_class)

        result = ModelTagManager.invalidate_model_tag("WrongModel", 42)
        assert result is False

    def test_connect_signals(self, mock_model_class):
        """Test that signals are connected when registering."""
        with patch.object(post_save, 'connect') as mock_save_connect, \
             patch.object(post_delete, 'connect') as mock_delete_connect:
            ModelTagManager.connect_signals(mock_model_class)

            mock_save_connect.assert_called_once()
            mock_delete_connect.assert_called_once()

    def test_disconnect_signals(self, mock_model_class):
        """Test that signals are disconnected when unregistering."""
        with patch.object(post_save, 'disconnect') as mock_save_disconnect, \
             patch.object(post_delete, 'disconnect') as mock_delete_disconnect:
            ModelTagManager.register_model(mock_model_class)
            ModelTagManager.disconnect_signals(mock_model_class)

            mock_save_disconnect.assert_called_once()
            mock_delete_disconnect.assert_called_once()

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_change_increments_tag(self, mock_standard_tag, mock_model_class, mock_model_instance):
        """Test that signal handler increments tag on model change."""
        # Setup
        ModelTagManager.register_model(mock_model_class)
        mock_tag_instance = MagicMock()
        mock_standard_tag.return_value = mock_tag_instance

        # Trigger signal
        ModelTagManager._on_model_change(
            sender=mock_model_class,
            instance=mock_model_instance,
            **{}
        )

        # Verify tag was created and incremented
        mock_standard_tag.assert_called_once()
        mock_tag_instance.increment.assert_called_once()

    def test_on_model_change_instance_without_pk(self, mock_model_class):
        """Test signal handler with instance without pk (should be silent)."""
        ModelTagManager.register_model(mock_model_class)

        instance = MagicMock()
        instance.pk = None

        # Should not raise exception
        ModelTagManager._on_model_change(
            sender=mock_model_class,
            instance=instance,
            **{}
        )

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_change_unregistered_model(self, mock_standard_tag):
        """Test signal handler for unregistered model (should be silent)."""
        mock_model = MagicMock()

        # Should not raise exception and StandardTag should not be called
        ModelTagManager._on_model_change(
            sender=mock_model,
            instance=MagicMock(),
            **{}
        )

        mock_standard_tag.assert_not_called()

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_change_exception_is_silenced(
        self, mock_standard_tag, mock_model_class, mock_model_instance
    ):
        """Signal handler silently catches exceptions (e.g. Redis down)."""
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag.increment.side_effect = ConnectionError("Redis down")
        mock_standard_tag.return_value = mock_tag

        # Should NOT raise
        ModelTagManager._on_model_change(
            sender=mock_model_class,
            instance=mock_model_instance,
        )

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_exception_returns_false(
        self, mock_standard_tag, mock_model_class
    ):
        """invalidate_model_tag returns False when increment raises."""
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag.increment.side_effect = ConnectionError("Redis down")
        mock_standard_tag.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)
        assert result is False

    @patch("django.apps.apps.get_model")
    def test_get_tag_name_for_model_via_app_label(
        self, mock_get_model, mock_model_class
    ):
        """get_tag_name_for_model falls back to apps.get_model lookup."""
        ModelTagManager.register_model(mock_model_class)

        # Use a different class object that's not directly in the registry
        other_ref = MagicMock()
        mock_get_model.return_value = mock_model_class  # maps back to registered class

        result = ModelTagManager.get_tag_name_for_model(other_ref)
        assert result == "MockModel"

    @patch("django.apps.apps.get_model")
    def test_get_tag_name_for_model_app_lookup_fails(
        self, mock_get_model
    ):
        """get_tag_name_for_model returns None when apps.get_model raises."""
        mock_get_model.side_effect = LookupError("No such model")

        unknown = MagicMock()
        result = ModelTagManager.get_tag_name_for_model(unknown)
        assert result is None


# Pytest fixtures
@pytest.fixture
def mock_model_class():
    """Mock Django model class."""
    model = MagicMock()
    model.__name__ = "MockModel"
    return model


@pytest.fixture
def mock_model_instance():
    """Mock Django model instance."""
    instance = MagicMock()
    instance.pk = 42
    return instance