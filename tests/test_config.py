"""Tests for fragmented_keys_django.config module."""

from unittest.mock import MagicMock, patch

import pytest

from fragmented_keys_django.config import (
    configure_fragmented_keys,
    get_cache_handler,
    get_global_prefix,
    reset_configuration,
    set_cache_handler_globally,
    set_global_prefix,
)


class TestConfigureFragmentedKeys:
    """Tests for configure_fragmented_keys()."""

    @patch("fragmented_keys.Configuration")
    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_default_params(self, mock_caches, mock_handler_cls, mock_config):
        """Default call uses cache 'default' and prefix 'NOZ'."""
        mock_config.get_default_cache_handler.side_effect = RuntimeError
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler

        configure_fragmented_keys(setup_key_ring=False)

        mock_handler_cls.assert_called_once_with("default")
        mock_config.set_default_cache_handler.assert_called_once_with(mock_handler)
        mock_config.set_global_prefix.assert_called_once_with("NOZ")

    @patch("fragmented_keys.Configuration")
    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_custom_cache_name_and_prefix(self, mock_caches, mock_handler_cls, mock_config):
        """Custom cache_name and prefix are forwarded."""
        mock_config.get_default_cache_handler.side_effect = RuntimeError
        mock_caches.__getitem__.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        configure_fragmented_keys(cache_name="redis_cache", prefix="MYAPP", setup_key_ring=False)

        mock_handler_cls.assert_called_once_with("redis_cache")
        mock_config.set_global_prefix.assert_called_once_with("MYAPP")

    @patch("fragmented_keys.Configuration")
    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_global_prefix_overrides_prefix(self, mock_caches, mock_handler_cls, mock_config):
        """global_prefix param takes precedence over prefix."""
        mock_config.get_default_cache_handler.side_effect = RuntimeError
        mock_caches.__getitem__.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        configure_fragmented_keys(prefix="IGNORED", global_prefix="WINNER", setup_key_ring=False)

        mock_config.set_global_prefix.assert_called_once_with("WINNER")

    @patch("fragmented_keys.Configuration")
    def test_skips_handler_creation_when_already_configured(self, mock_config):
        """When handler already exists, only updates prefix (no recursion)."""
        mock_config.get_default_cache_handler.return_value = MagicMock()

        configure_fragmented_keys(prefix="GNP", setup_key_ring=False)

        mock_config.set_global_prefix.assert_called_once_with("GNP")
        mock_config.set_default_cache_handler.assert_not_called()


class TestGetCacheHandler:
    """Tests for get_cache_handler()."""

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_returns_handler_for_alias(self, mock_caches, mock_handler_cls):
        """Returns a DjangoCacheHandler wrapping the requested alias."""
        mock_caches.__getitem__.return_value = MagicMock()
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler

        result = get_cache_handler("my_cache")

        mock_handler_cls.assert_called_once_with("my_cache")
        assert result is mock_handler

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_default_alias(self, mock_caches, mock_handler_cls):
        """Defaults to 'default' when no alias provided."""
        mock_caches.__getitem__.return_value = MagicMock()
        mock_handler_cls.return_value = MagicMock()

        get_cache_handler()

        mock_handler_cls.assert_called_once_with("default")


class TestResetConfiguration:
    """Tests for reset_configuration()."""

    @patch("fragmented_keys_django.cache_utils.key_rings.clear_key_rings")
    @patch("fragmented_keys.Configuration")
    def test_calls_reset(self, mock_config, mock_clear_rings):
        """Delegates to Configuration.reset() and clears key rings."""
        reset_configuration()

        mock_config.reset.assert_called_once()
        mock_clear_rings.assert_called_once()


class TestSetCacheHandlerGlobally:
    """Tests for set_cache_handler_globally()."""

    @patch("fragmented_keys.Configuration")
    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_replaces_global_handler(self, mock_caches, mock_handler_cls, mock_config):
        """Creates new handler and sets it as global default."""
        mock_caches.__getitem__.return_value = MagicMock()
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler

        set_cache_handler_globally("memcached_cache")

        mock_handler_cls.assert_called_once_with("memcached_cache")
        mock_config.set_default_cache_handler.assert_called_once_with(mock_handler)


class TestSetGlobalPrefix:
    """Tests for set_global_prefix()."""

    @patch("fragmented_keys.Configuration")
    def test_sets_prefix(self, mock_config):
        """Delegates to Configuration.set_global_prefix()."""
        set_global_prefix("PRODUCTION")

        mock_config.set_global_prefix.assert_called_once_with("PRODUCTION")


class TestGetGlobalPrefix:
    """Tests for get_global_prefix()."""

    @patch("fragmented_keys.Configuration")
    def test_returns_prefix(self, mock_config):
        """Delegates to Configuration.get_global_prefix()."""
        mock_config.get_global_prefix.return_value = "MYPREFIX"

        result = get_global_prefix()

        assert result == "MYPREFIX"
        mock_config.get_global_prefix.assert_called_once()
