"""Tests for @tagged_cache decorator."""

from unittest.mock import MagicMock, patch, call
from functools import wraps

import pytest

from fragmented_keys_django.cache_utils.decorators import (
    tagged_cache,
    resolve_param_value,
    parse_tag_template,
    resolve_tag_instance,
)


class TestTaggedCacheDecorator:
    """Tests for the @tagged_cache decorator."""

    @patch("django.core.cache.caches")
    def test_decorator_cache_miss(self, mock_caches):
        """Test decorator on cache miss."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache

        call_count = 0

        @tagged_cache(
            timeout=3600,
            tags=["User:{user_id}"],
            vary_on=["user_id"],
        )
        def get_user_data(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "data": "test"}

        # First call - cache miss
        result1 = get_user_data(42)
        assert result1 == {"id": 42, "data": "test"}
        assert call_count == 1
        assert mock_cache.set.called

    @patch("django.core.cache.caches")
    def test_decorator_cache_hit(self, mock_caches):
        """Test decorator on cache hit."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"id": 42, "data": "cached"}
        mock_caches.__getitem__.return_value = mock_cache

        call_count = 0

        @tagged_cache(
            timeout=3600,
            tags=["User:{user_id}"],
            vary_on=["user_id"],
        )
        def get_user_data(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "data": "test"}

        # First call - cache hit
        result1 = get_user_data(42)
        assert result1 == {"id": 42, "data": "cached"}
        assert call_count == 0
        assert not mock_cache.set.called

    @patch("django.core.cache.caches")
    def test_decorator_with_multiple_tags(self, mock_caches):
        """Test decorator with multiple tags."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache

        @tagged_cache(
            timeout=3600,
            tags=["User:{user_id}", "Campaign:{campaign_id}", "Dashboard"],
            vary_on=["user_id", "campaign_id"],
        )
        def get_campaign_stats(user_id: int, campaign_id: int):
            return {"user": user_id, "campaign": campaign_id}

        result = get_campaign_stats(42, 100)
        assert result == {"user": 42, "campaign": 100}
        assert mock_cache.get.called

    @patch("django.core.cache.caches")
    def test_decorator_custom_key_name(self, mock_caches):
        """Test decorator with custom key name."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache

        @tagged_cache(
            key_name="CustomKey",
            tags=["Test"],
        )
        def my_function():
            return "result"

        my_function()
        assert mock_cache.get.called
        # The generated cache key should be based on "CustomKey"

    @patch("django.core.cache.caches")
    def test_decorator_with_version(self, mock_caches):
        """Test decorator with version parameter."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache

        @tagged_cache(
            version="v2",
            tags=["Test"],
        )
        def my_function():
            return "result"

        my_function()
        assert mock_cache.get.called

    @patch("fragmented_keys.tag.base.Configuration")
    @patch("django.core.cache.caches")
    def test_decorator_custom_cache_name(self, mock_caches, mock_config):
        """Test decorator with custom cache name."""
        mock_handler = MagicMock()
        mock_config.get_default_cache_handler.return_value = mock_handler
        mock_config.get_global_prefix.return_value = ""
        mock_handler.get.return_value = "1.0"

        mock_cache1 = MagicMock()
        mock_cache1.get.return_value = None
        mock_cache2 = MagicMock()
        mock_cache2.get.return_value = None

        mock_caches.__getitem__.side_effect = lambda name: {
            "default": mock_cache1,
            "custom": mock_cache2,
        }[name]

        @tagged_cache(
            cache_name="custom",
            tags=["Test"],
        )
        def my_function():
            return "result"

        my_function()
        assert not mock_cache1.get.called
        assert mock_cache2.get.called

    @patch("django.core.cache.caches")
    def test_decorator_on_method(self, mock_caches):
        """Test decorator on class method."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache

        class TestService:
            @tagged_cache(
                tags=["Service:{id}"],
                vary_on=["id"],
            )
            def get_data(self, id: int):
                return {"id": id}

        service = TestService()
        result = service.get_data(42)
        assert result == {"id": 42}


class TestResolveParamValue:
    """Tests for resolve_param_value helper."""

    def test_resolve_from_kwargs(self):
        """Test resolving parameter from kwargs."""
        def test_func(param1, param2):
            pass

        result = resolve_param_value("param1", (), {"param1": "value1"}, test_func)
        assert result == "value1"

    def test_resolve_from_args(self):
        """Test resolving parameter from positional args."""
        def test_func(param1, param2):
            pass

        result = resolve_param_value("param1", ("value1", "value2"), {}, test_func)
        assert result == "value1"

    def test_resolve_not_found(self):
        """Test resolving parameter that doesn't exist."""
        def test_func(param1):
            pass

        with pytest.raises(KeyError):
            resolve_param_value("nonexistent", (), {}, test_func)

    def test_resolve_method_self(self):
        """Test resolving self parameter in method."""
        class TestClass:
            def method(self, param):
                pass

        instance = TestClass()
        result = resolve_param_value("self", (instance,), {}, TestClass.method)
        assert result is instance

    def test_resolve_second_positional_arg(self):
        """Test resolving second positional argument."""
        def test_func(param1, param2, param3):
            pass

        result = resolve_param_value("param2", ("a", "b", "c"), {}, test_func)
        assert result == "b"


class TestParseTagTemplate:
    """Tests for parse_tag_template helper."""

    def test_parse_with_placeholder(self):
        """Test parsing tag template with placeholder."""
        tag_name, pattern = parse_tag_template("User:{user_id}")
        assert tag_name == "User"
        assert pattern == "{user_id}"

    def test_parse_without_placeholder(self):
        """Test parsing tag template without placeholder."""
        tag_name, pattern = parse_tag_template("Dashboard")
        assert tag_name == "Dashboard"
        assert pattern == ""

    def test_parse_with_multiple_placeholders(self):
        """Test parsing tag template with multiple parts."""
        tag_name, pattern = parse_tag_template("Prefix:{variable}:Suffix")
        # Only the first placeholder is extracted
        assert tag_name == "Prefix"
        assert pattern == "{variable}"


class TestResolveTagInstance:
    """Tests for resolve_tag_instance helper."""

    def test_resolve_with_kwargs(self):
        """Test resolving tag instance from kwargs."""
        tag_template = "User:{user_id}"

        def test_func(user_id):
            pass

        result = resolve_tag_instance(tag_template, (), {"user_id": 42}, test_func)
        assert result == "42"

    def test_resolve_with_args(self):
        """Test resolving tag instance from args."""
        tag_template = "User:{user_id}"

        def test_func(user_id):
            pass

        result = resolve_tag_instance(tag_template, (42,), {}, test_func)
        assert result == "42"

    def test_resolve_no_placeholder(self):
        """Test resolving tag without placeholder returns empty."""
        tag_template = "Dashboard"

        def test_func():
            pass

        result = resolve_tag_instance(tag_template, (), {}, test_func)
        assert result == ""

    def test_resolve_missing_param(self):
        """Test resolving tag when param is missing returns empty."""
        tag_template = "User:{missing}"

        def test_func(user_id):
            pass

        result = resolve_tag_instance(tag_template, (42,), {}, test_func)
        assert result == ""