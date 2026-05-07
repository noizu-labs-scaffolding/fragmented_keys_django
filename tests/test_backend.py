"""Tests for FragmentedKeysCacheBackend."""

from unittest.mock import MagicMock, patch, ANY
import pytest
import pickle

from fragmented_keys import StandardTag, FragmentedKeyRing
from fragmented_keys_django.cache_backends.django_backend import FragmentedKeysCacheBackend


class TestFragmentedKeysCacheBackend:
    """Tests for the FragmentedKeysCacheBackend Django cache backend."""

    @pytest.fixture
    def backend_params(self):
        """Default backend parameters for testing."""
        return {
            "CACHE_NAME": "default",
            "PREFIX": "TEST",
        }

    @patch("fragmented_keys.Configuration")
    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_backend_initialization(
        self, mock_caches, mock_handler_class, mock_config, backend_params
    ):
        """Test backend initialization."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)

        assert backend._cache_name == "default"
        assert backend._prefix == "TEST"
        mock_config.set_default_cache_handler.assert_called_once()
        mock_config.set_global_prefix.assert_called_once_with("TEST")

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_get_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend get method."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "cached_value"
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.get("test_key")

        assert result == "cached_value"
        mock_cache.get.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_get_method_with_default(self, mock_caches, mock_handler_class, backend_params):
        """Test backend get method with default value."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.get("test_key", default="default_value")

        assert result == "default_value"

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_set_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend set method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.set("test_key", "test_value", timeout=3600)

        mock_cache.set.assert_called_once_with(
            backend.make_key("test_key"),
            "test_value",
            timeout=3600
        )

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_add_method_success(self, mock_caches, mock_handler_class, backend_params):
        """Test backend add method on success."""
        mock_cache = MagicMock()
        mock_cache.add.return_value = True
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.add("test_key", "test_value")

        assert result is True
        mock_cache.add.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_add_method_key_exists(self, mock_caches, mock_handler_class, backend_params):
        """Test backend add method when key already exists."""
        mock_cache = MagicMock()
        mock_cache.add.return_value = False
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.add("test_key", "test_value")

        assert result is False

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_delete_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend delete method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.delete("test_key")

        mock_cache.delete.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_get_many_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend get_many method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)

        # Build the expected cache keys so the mock returns matching keys
        cache_key1 = backend.make_key("key1")
        cache_key2 = backend.make_key("key2")
        mock_cache.get_many.return_value = {
            cache_key1: "value1",
            cache_key2: "value2",
        }

        result = backend.get_many(["key1", "key2"])

        assert len(result) == 2
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"
        mock_cache.get_many.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_set_many_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend set_many method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.set_many({"key1": "value1", "key2": "value2"}, timeout=3600)

        assert result == []
        mock_cache.set_many.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_delete_many_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend delete_many method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.delete_many(["key1", "key2"])

        mock_cache.delete_many.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_has_key_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend has_key method."""
        mock_cache = MagicMock()
        mock_cache.has_key.return_value = True
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.has_key("test_key")

        assert result is True

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_clear_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend clear method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.clear()

        mock_cache.clear.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_get_or_set_method_hit(self, mock_caches, mock_handler_class, backend_params):
        """Test backend get_or_set method on cache hit."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "cached_value"
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.get_or_set("test_key", "default_value")

        assert result == "cached_value"
        mock_cache.set.assert_not_called()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_get_or_set_method_miss(self, mock_caches, mock_handler_class, backend_params):
        """Test backend get_or_set method on cache miss."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.get_or_set("test_key", "default_value")

        assert result == "default_value"
        mock_cache.set.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_touch_method_supported(self, mock_caches, mock_handler_class, backend_params):
        """Test backend touch method when supported."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.touch("test_key", timeout=3600)

        assert result is True
        mock_cache.touch.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_touch_method_unsupported(self, mock_caches, mock_handler_class, backend_params):
        """Test backend touch method when not supported."""
        mock_cache = MagicMock()
        mock_cache.touch.side_effect = AttributeError()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.touch("test_key")

        assert result is False

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_incr_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend incr method."""
        mock_cache = MagicMock()
        mock_cache.has_key.return_value = True
        mock_cache.incr.return_value = 5
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.incr("test_key", delta=2)

        assert result == 5

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_incr_method_key_not_found(self, mock_caches, mock_handler_class, backend_params):
        """Test backend incr method when key doesn't exist."""
        mock_cache = MagicMock()
        mock_cache.has_key.return_value = False
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)

        with pytest.raises(ValueError):
            backend.incr("test_key")

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_decr_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend decr method."""
        mock_cache = MagicMock()
        mock_cache.has_key.return_value = True
        mock_cache.decr.return_value = 3
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        result = backend.decr("test_key", delta=2)

        assert result == 3

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_close_method(self, mock_caches, mock_handler_class, backend_params):
        """Test backend close method."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.close()

        mock_cache.close.assert_called_once()

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_close_method_unsupported(self, mock_caches, mock_handler_class, backend_params):
        """Test backend close method when not supported."""
        mock_cache = MagicMock()
        mock_cache.close.side_effect = AttributeError()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend("", backend_params)
        # Should not raise exception
        backend.close()

    def test_make_key_versioning(self, backend_params):
        """Test that make_key properly handles version parameter."""
        backend = FragmentedKeysCacheBackend("", backend_params)

        with patch.object(backend, "key_prefix", ""):
            key_v1 = backend.make_key("test_key", version=1)
            key_v2 = backend.make_key("test_key", version=2)

            assert key_v1 != key_v2

    def test_make_key_versioning_produces_different_keys(self, backend_params):
        """Test that make_key with different versions produces different keys."""
        backend = FragmentedKeysCacheBackend("", backend_params)

        with patch.object(backend, "key_prefix", ""):
            key_v1 = backend.make_key("test_key", version=1)
            key_v2 = backend.make_key("test_key", version=2)

            # Different versions should produce different cache keys
            assert key_v1 != key_v2

    def test_get_backend_timeout_default(self, backend_params):
        """Test get_backend_timeout with default timeout."""
        backend = FragmentedKeysCacheBackend("", backend_params)
        backend.default_timeout = 300

        timeout = backend.get_backend_timeout(None)
        assert timeout == 300

    def test_get_backend_timeout_explicit(self, backend_params):
        """Test get_backend_timeout with explicit timeout."""
        backend = FragmentedKeysCacheBackend("", backend_params)

        timeout = backend.get_backend_timeout(600)
        assert timeout == 600


class TestTagAwareMethods:
    """Tests for tag-aware methods on FragmentedKeysCacheBackend."""

    @pytest.fixture
    def backend(self):
        """Create a backend instance with a real in-memory cache mock."""
        params = {"CACHE_NAME": "default", "PREFIX": "TEST"}
        backend = FragmentedKeysCacheBackend("", params)
        return backend

    @pytest.fixture
    def tags_tuples(self):
        """Sample tags as tuples."""
        return [("User", "42"), ("Campaign", "7")]

    def test_set_get_roundtrip_with_tuples(self, backend, tags_tuples):
        """set_with_tags then get_with_tags returns the cached value."""
        backend.set_with_tags("profile", {"name": "Alice"}, tags_tuples)
        result = backend.get_with_tags("profile", tags_tuples)
        assert result == {"name": "Alice"}

    def test_set_get_roundtrip_with_standard_tags(self, backend):
        """Tags can be StandardTag objects instead of tuples."""
        tags = [
            StandardTag("User", "42", handler=backend._handler),
            StandardTag("Campaign", "7", handler=backend._handler),
        ]
        backend.set_with_tags("profile", "value", tags)
        result = backend.get_with_tags("profile", tags)
        assert result == "value"

    def test_get_miss_returns_default(self, backend, tags_tuples):
        """get_with_tags returns default on cache miss."""
        result = backend.get_with_tags("missing", tags_tuples, default="fallback")
        assert result == "fallback"

    def test_get_miss_returns_none_by_default(self, backend, tags_tuples):
        """get_with_tags returns None when no default specified."""
        result = backend.get_with_tags("missing", tags_tuples)
        assert result is None

    def test_invalidation_causes_miss(self, backend, tags_tuples):
        """After invalidate_tags, get_with_tags returns default (cache miss)."""
        backend.set_with_tags("profile", "cached", tags_tuples)
        # Verify it's there
        assert backend.get_with_tags("profile", tags_tuples) == "cached"
        # Invalidate
        count = backend.invalidate_tags(tags_tuples)
        assert count == 2
        # Now it should miss — key string changed because tag versions changed
        assert backend.get_with_tags("profile", tags_tuples) is None

    def test_invalid_tag_input_raises_type_error(self, backend):
        """Passing invalid tag types raises TypeError."""
        with pytest.raises(TypeError):
            backend._normalize_tags(["just_a_string"])

        with pytest.raises(TypeError):
            backend._normalize_tags([123])

    def test_3_tuple_constant_tag(self, backend):
        """3-tuple with 'constant' creates a ConstantTag."""
        from fragmented_keys import ConstantTag
        tags = backend._normalize_tags([("env", "prod", "constant")])
        assert len(tags) == 1
        assert isinstance(tags[0], ConstantTag)

    def test_3_tuple_invalid_type_raises(self, backend):
        """3-tuple with invalid type raises TypeError."""
        with pytest.raises(TypeError, match="must be 'constant'"):
            backend._normalize_tags([("a", "b", "invalid")])

    def test_dict_tag_standard(self, backend):
        """Dict with type='standard' creates a StandardTag."""
        from fragmented_keys import StandardTag
        tags = backend._normalize_tags([{"tag": "user", "instance": "42"}])
        assert len(tags) == 1
        assert isinstance(tags[0], StandardTag)

    def test_dict_tag_constant(self, backend):
        """Dict with type='constant' creates a ConstantTag."""
        from fragmented_keys import ConstantTag
        tags = backend._normalize_tags([
            {"tag": "api", "instance": "v2", "type": "constant", "version": 2.0}
        ])
        assert len(tags) == 1
        assert isinstance(tags[0], ConstantTag)
        assert tags[0].get_tag_version() == 2.0

    def test_1_tuple_deprecated(self, backend):
        """1-tuple works but emits DeprecationWarning."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tags = backend._normalize_tags([("user",)])
            assert len(tags) == 1
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_base_tag_passthrough(self, backend):
        """Raw ConstantTag instances pass through unchanged."""
        from fragmented_keys import ConstantTag
        raw = ConstantTag("env", "prod", version=1.0)
        tags = backend._normalize_tags([raw])
        assert tags[0] is raw

    def test_delete_with_tags(self, backend, tags_tuples):
        """delete_with_tags removes the composite entry."""
        backend.set_with_tags("profile", "cached", tags_tuples)
        assert backend.get_with_tags("profile", tags_tuples) == "cached"
        backend.delete_with_tags("profile", tags_tuples)
        assert backend.get_with_tags("profile", tags_tuples) is None

    def test_get_or_set_miss_with_value(self, backend, tags_tuples):
        """get_or_set_with_tags sets and returns default on miss."""
        result = backend.get_or_set_with_tags("profile", "computed", tags_tuples)
        assert result == "computed"
        # Now it should be cached
        assert backend.get_with_tags("profile", tags_tuples) == "computed"

    def test_get_or_set_miss_with_callable(self, backend, tags_tuples):
        """get_or_set_with_tags calls callable default on miss."""
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return "expensive_result"

        result = backend.get_or_set_with_tags("callable_key", compute, tags_tuples)
        assert result == "expensive_result"
        assert call_count == 1
        # Second call should hit cache, not call compute again
        result2 = backend.get_or_set_with_tags("callable_key", compute, tags_tuples)
        assert result2 == "expensive_result"
        assert call_count == 1

    def test_get_or_set_hit(self, backend, tags_tuples):
        """get_or_set_with_tags returns cached value on hit."""
        backend.set_with_tags("profile", "existing", tags_tuples)
        result = backend.get_or_set_with_tags("profile", "should_not_use", tags_tuples)
        assert result == "existing"

    def test_get_tag_version(self, backend):
        """get_tag_version returns a numeric version."""
        version = backend.get_tag_version("User", "42")
        assert isinstance(version, float)

    def test_create_key_ring(self, backend):
        """create_key_ring returns a pre-configured FragmentedKeyRing."""
        ring = backend.create_key_ring()
        assert isinstance(ring, FragmentedKeyRing)

    def test_group_id_produces_different_keys(self, backend, tags_tuples):
        """Different group_id values produce different composite keys."""
        key1 = backend._build_tagged_key("profile", tags_tuples, group_id="g1")
        key2 = backend._build_tagged_key("profile", tags_tuples, group_id="g2")
        assert key1 != key2

    def test_standard_get_set_still_work(self, backend):
        """Existing passthrough get/set methods are unaffected."""
        backend.set("plain_key", "plain_value", timeout=60)
        result = backend.get("plain_key")
        assert result == "plain_value"

    def test_mixed_tag_types(self, backend):
        """Can mix StandardTag objects and tuples in the same list."""
        tags = [
            StandardTag("User", "42", handler=backend._handler),
            ("Campaign", "7"),
        ]
        backend.set_with_tags("mixed", "data", tags)
        result = backend.get_with_tags("mixed", tags)
        assert result == "data"


class TestBackendModes:
    """Tests for delegation vs standalone mode selection."""

    def test_cache_name_and_location_raises(self):
        """Specifying both CACHE_NAME and LOCATION raises ValueError."""
        params = {
            "CACHE_NAME": "default",
            "PREFIX": "TEST",
        }
        with pytest.raises(ValueError, match="not both"):
            FragmentedKeysCacheBackend("redis://127.0.0.1:6379/1", params)

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_delegation_mode_uses_cache_name(
        self, mock_caches, mock_handler_class
    ):
        """CACHE_NAME triggers delegation mode."""
        mock_cache = MagicMock()
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend(
            "", {"CACHE_NAME": "my_redis", "PREFIX": "TEST"}
        )
        assert backend._cache_name == "my_redis"
        mock_handler_class.assert_called_once_with("my_redis")

    @patch("fragmented_keys.Configuration")
    @patch(
        "fragmented_keys_django.cache_backends.django_backend.import_string"
    )
    def test_standalone_mode_via_server_arg(
        self, mock_import, mock_config
    ):
        """Server arg (from Django LOCATION) triggers standalone mode."""
        mock_backend_cls = MagicMock()
        mock_underlying = MagicMock()
        mock_backend_cls.return_value = mock_underlying
        mock_import.return_value = mock_backend_cls

        params = {"PREFIX": "STANDALONE"}
        backend = FragmentedKeysCacheBackend("redis://127.0.0.1:6379/2", params)

        mock_import.assert_called_once_with(
            "django.core.cache.backends.redis.RedisCache"
        )
        mock_backend_cls.assert_called_once_with(
            "redis://127.0.0.1:6379/2", params
        )
        assert backend._cache_name == "standalone"
        assert backend._prefix == "STANDALONE"

    @patch("fragmented_keys.Configuration")
    @patch(
        "fragmented_keys_django.cache_backends.django_backend.import_string"
    )
    def test_standalone_mode_via_params_location(
        self, mock_import, mock_config
    ):
        """LOCATION in params also triggers standalone mode (fallback)."""
        mock_backend_cls = MagicMock()
        mock_underlying = MagicMock()
        mock_backend_cls.return_value = mock_underlying
        mock_import.return_value = mock_backend_cls

        params = {
            "LOCATION": "redis://127.0.0.1:6379/2",
            "PREFIX": "STANDALONE",
        }
        backend = FragmentedKeysCacheBackend("", params)

        assert backend._cache_name == "standalone"

    @patch("fragmented_keys.Configuration")
    @patch(
        "fragmented_keys_django.cache_backends.django_backend.import_string"
    )
    def test_standalone_mode_custom_backend_class(
        self, mock_import, mock_config
    ):
        """BACKEND_CLASS overrides the default Django Redis backend."""
        mock_backend_cls = MagicMock()
        mock_import.return_value = mock_backend_cls

        params = {
            "BACKEND_CLASS": "django.core.cache.backends.memcached.PyMemcacheCache",
            "PREFIX": "MC",
        }
        FragmentedKeysCacheBackend("memcached://127.0.0.1:11211", params)

        mock_import.assert_called_once_with(
            "django.core.cache.backends.memcached.PyMemcacheCache"
        )

    def test_no_cache_name_no_location_defaults_to_delegation(self):
        """Omitting both CACHE_NAME and LOCATION defaults to delegation with 'default'."""
        params = {"PREFIX": "TEST"}
        backend = FragmentedKeysCacheBackend("", params)
        assert backend._cache_name == "default"

    @patch("fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler")
    @patch("django.core.cache.caches")
    def test_decr_key_not_found(self, mock_caches, mock_handler_class):
        """decr raises ValueError when key doesn't exist."""
        mock_cache = MagicMock()
        mock_cache.has_key.return_value = False
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler

        backend = FragmentedKeysCacheBackend(
            "", {"CACHE_NAME": "default", "PREFIX": "TEST"}
        )

        with pytest.raises(ValueError):
            backend.decr("missing_key")