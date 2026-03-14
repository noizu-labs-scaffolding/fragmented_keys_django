"""Tests for DjangoCacheHandler."""

import json
from unittest.mock import MagicMock, patch

import pytest

from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler


class TestDjangoCacheHandler:
    """Tests for DjangoCacheHandler adapter class."""

    def test_group_name(self, mock_django_cache):
        """Test that group_name returns a unique identifier."""
        handler = DjangoCacheHandler("test_cache")
        group_name = handler.group_name()

        assert "DjangoCacheHandler" in group_name
        assert "MockCache" in group_name
        assert "test_cache" in group_name

    def test_get_string(self, mock_django_cache):
        """Test get operation with string values."""
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "test_value"

    def test_get_bytes(self, mock_django_cache_bytes):
        """Test get operation with bytes values."""
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "test_value"
        assert isinstance(result, str)

    def test_get_dict(self, mock_django_cache_dict):
        """Test get operation with dict values."""
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_get_none(self, mock_django_cache_none):
        """Test get operation when value is None."""
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result is None

    def test_set_with_ttl(self, mock_django_cache):
        """Test set operation with TTL."""
        handler = DjangoCacheHandler("test_cache")

        handler.set("test_key", "test_value", ttl=3600)

        mock_django_cache.set.assert_called_once_with("test_key", "test_value", timeout=3600)

    def test_set_without_ttl(self, mock_django_cache):
        """Test set operation without TTL."""
        handler = DjangoCacheHandler("test_cache")

        handler.set("test_key", "test_value")

        mock_django_cache.set.assert_called_once_with("test_key", "test_value", timeout=None)

    def test_get_multi(self, mock_django_cache):
        """Test get_multi operation."""
        mock_django_cache.get_many.return_value = {
            "key1": "value1",
            "key2": "value2",
        }

        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1", "key2", "key3"])

        assert result == {"key1": "value1", "key2": "value2"}

    def test_get_multi_with_dict_values(self, mock_django_cache_multi_dict):
        """Test get_multi with dict values."""
        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1", "key2"])

        assert "key1" in result
        assert "key2" in result
        assert isinstance(result["key1"], str)

    def test_get_multi_empty_result(self, mock_django_cache):
        """Test get_multi when no keys are found."""
        mock_django_cache.get_many.return_value = {}

        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1", "key2"])

        assert result == {}

    def test_get_int_value(self, mock_django_cache):
        """Test get converts int values to string."""
        mock_django_cache.get.return_value = 42
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "42"
        assert isinstance(result, str)

    def test_get_float_value(self, mock_django_cache):
        """Test get converts float values to string."""
        mock_django_cache.get.return_value = 3.14
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "3.14"
        assert isinstance(result, str)

    def test_get_bool_value(self, mock_django_cache):
        """Test get converts bool values to string."""
        mock_django_cache.get.return_value = True
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "True"
        assert isinstance(result, str)

    def test_get_complex_object_fallback(self, mock_django_cache):
        """Test get falls back to str() for complex objects."""
        obj = object()
        mock_django_cache.get.return_value = obj
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == str(obj)

    def test_get_complex_object_str_fails(self, mock_django_cache):
        """Test get returns None when str() raises on complex object."""
        class Unstringable:
            def __str__(self):
                raise RuntimeError("cannot stringify")

        mock_django_cache.get.return_value = Unstringable()
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result is None

    def test_get_list_value(self, mock_django_cache):
        """Test get converts list values to JSON string."""
        mock_django_cache.get.return_value = [1, 2, 3]
        handler = DjangoCacheHandler("test_cache")

        result = handler.get("test_key")
        assert result == "[1, 2, 3]"
        assert isinstance(result, str)

    def test_get_multi_with_none_value(self, mock_django_cache):
        """Test get_multi skips None values."""
        mock_django_cache.get_many.return_value = {
            "key1": "value1",
            "key2": None,
        }
        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1", "key2"])
        assert result == {"key1": "value1"}

    def test_get_multi_with_bytes_value(self, mock_django_cache):
        """Test get_multi converts bytes values."""
        mock_django_cache.get_many.return_value = {
            "key1": b"bytes_value",
        }
        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1"])
        assert result == {"key1": "bytes_value"}

    def test_get_multi_with_int_value(self, mock_django_cache):
        """Test get_multi converts int values via str()."""
        mock_django_cache.get_many.return_value = {
            "key1": 99,
        }
        handler = DjangoCacheHandler("test_cache")

        result = handler.get_multi(["key1"])
        assert result == {"key1": "99"}

    def test_init_with_cache_instance(self, mock_django_cache):
        """Test constructing handler with a cache instance directly."""
        handler = DjangoCacheHandler(cache_name="standalone", cache=mock_django_cache)

        assert handler._cache is mock_django_cache
        assert handler._cache_name == "standalone"

        # Should work for get/set
        mock_django_cache.get.return_value = "direct_value"
        assert handler.get("key") == "direct_value"


# Pytest fixtures
@pytest.fixture
def mock_django_cache():
    """Mock Django cache instance."""
    with patch("django.core.cache.caches") as mock_caches:
        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.get.return_value = "test_value"
        mock_cache.get_many.return_value = {"test_key": "test_value"}
        mock_caches.__getitem__.return_value = mock_cache
        yield mock_cache


@pytest.fixture
def mock_django_cache_bytes():
    """Mock Django cache with bytes value."""
    with patch("django.core.cache.caches") as mock_caches:
        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.get.return_value = b"test_value"
        mock_caches.__getitem__.return_value = mock_cache
        yield mock_cache


@pytest.fixture
def mock_django_cache_dict():
    """Mock Django cache with dict value."""
    with patch("django.core.cache.caches") as mock_caches:
        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.get.return_value = {"key": "value"}
        mock_caches.__getitem__.return_value = mock_cache
        yield mock_cache


@pytest.fixture
def mock_django_cache_none():
    """Mock Django cache with None value."""
    with patch("django.core.cache.caches") as mock_caches:
        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache
        yield mock_cache


@pytest.fixture
def mock_django_cache_multi_dict():
    """Mock Django cache with dict values in get_many."""
    with patch("django.core.cache.caches") as mock_caches:
        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.get_many.return_value = {
            "key1": {"key": "value1"},
            "key2": {"key": "value2"},
        }
        mock_caches.__getitem__.return_value = mock_cache
        yield mock_cache