"""Integration tests against a real Redis instance.

These tests require Redis running on localhost:6379.
They use database 15 to avoid collisions with application data.
"""

import pytest

from fragmented_keys import Configuration, StandardKey, StandardTag

from fragmented_keys_django.cache_backends.django_backend import (
    FragmentedKeysCacheBackend,
)
from fragmented_keys_django.cache_backends.handlers import DjangoCacheHandler
from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager
from fragmented_keys_django.config import configure_fragmented_keys


pytestmark = pytest.mark.integration


# ── DjangoCacheHandler against Redis ──────────────────────────────────


class TestHandlerRedis:
    """DjangoCacheHandler integration with a real Redis backend."""

    @pytest.fixture(autouse=True)
    def handler(self, redis_cache):
        self.handler = DjangoCacheHandler("redis")
        yield
        Configuration.reset()

    def test_get_set_roundtrip(self):
        self.handler.set("h:key1", "hello", ttl=60)
        assert self.handler.get("h:key1") == "hello"

    def test_get_miss_returns_none(self):
        assert self.handler.get("h:nonexistent") is None

    def test_set_with_ttl(self):
        self.handler.set("h:ttl", "expires", ttl=1)
        assert self.handler.get("h:ttl") == "expires"

    def test_get_multi(self):
        self.handler.set("h:a", "1")
        self.handler.set("h:b", "2")
        result = self.handler.get_multi(["h:a", "h:b", "h:missing"])
        assert result == {"h:a": "1", "h:b": "2"}

    def test_get_multi_empty(self):
        result = self.handler.get_multi(["h:nothing1", "h:nothing2"])
        assert result == {}

    def test_overwrite(self):
        self.handler.set("h:ow", "first")
        self.handler.set("h:ow", "second")
        assert self.handler.get("h:ow") == "second"


# ── Tag versioning against Redis ──────────────────────────────────────


class TestTagVersioningRedis:
    """StandardTag version increments against real Redis."""

    @pytest.fixture(autouse=True)
    def setup(self, redis_cache):
        self.handler = DjangoCacheHandler("redis")
        Configuration.set_default_cache_handler(self.handler)
        Configuration.set_global_prefix("TEST_INT")
        yield
        Configuration.reset()

    def test_tag_starts_at_zero(self):
        tag = StandardTag("Fresh", "1", handler=self.handler)
        # First read — tag doesn't exist yet
        version = tag.get_tag_version()
        assert isinstance(version, (int, float))

    def test_tag_increment_changes_version(self):
        tag = StandardTag("Incr", "1", handler=self.handler)
        v1 = tag.get_tag_version()
        tag.increment()
        v2 = tag.get_tag_version()
        assert v2 != v1

    def test_independent_tags_independent_versions(self):
        tag_a = StandardTag("IndA", "1", handler=self.handler)
        tag_b = StandardTag("IndB", "1", handler=self.handler)
        tag_a.increment()
        va = tag_a.get_tag_version()
        vb = tag_b.get_tag_version()
        # tag_b was never incremented, so versions should differ
        assert va != vb

    def test_key_composition_changes_after_increment(self):
        tags = [
            StandardTag("KeyComp", "42", handler=self.handler),
        ]
        key = StandardKey("profile", tags)
        k1 = key.get_key_str(hash=True)

        tags[0].increment()
        # Re-create key with same params — version changed, so key string differs
        tags2 = [StandardTag("KeyComp", "42", handler=self.handler)]
        key2 = StandardKey("profile", tags2)
        k2 = key2.get_key_str(hash=True)

        assert k1 != k2


# ── FragmentedKeysCacheBackend (delegation mode) against Redis ────────


class TestBackendDelegationRedis:
    """FragmentedKeysCacheBackend in delegation mode against real Redis."""

    @pytest.fixture(autouse=True)
    def backend(self, redis_cache):
        params = {"CACHE_NAME": "redis", "PREFIX": "INT_DEL"}
        self.backend = FragmentedKeysCacheBackend(params)
        yield
        Configuration.reset()

    # ── Standard pass-through ──

    def test_set_get(self):
        self.backend.set("pt:key", "value", timeout=60)
        assert self.backend.get("pt:key") == "value"

    def test_get_default(self):
        assert self.backend.get("pt:miss", default="fallback") == "fallback"

    def test_add(self):
        assert self.backend.add("pt:add", "first", timeout=60) is True
        assert self.backend.add("pt:add", "second", timeout=60) is False
        assert self.backend.get("pt:add") == "first"

    def test_delete(self):
        self.backend.set("pt:del", "gone", timeout=60)
        self.backend.delete("pt:del")
        assert self.backend.get("pt:del") is None

    def test_get_many(self):
        self.backend.set("pt:m1", "a", timeout=60)
        self.backend.set("pt:m2", "b", timeout=60)
        result = self.backend.get_many(["pt:m1", "pt:m2", "pt:m3"])
        assert result == {"pt:m1": "a", "pt:m2": "b"}

    def test_set_many(self):
        self.backend.set_many({"pt:sm1": "x", "pt:sm2": "y"}, timeout=60)
        assert self.backend.get("pt:sm1") == "x"
        assert self.backend.get("pt:sm2") == "y"

    def test_delete_many(self):
        self.backend.set_many({"pt:dm1": "a", "pt:dm2": "b"}, timeout=60)
        self.backend.delete_many(["pt:dm1", "pt:dm2"])
        assert self.backend.get("pt:dm1") is None
        assert self.backend.get("pt:dm2") is None

    def test_has_key(self):
        self.backend.set("pt:hk", "yes", timeout=60)
        assert self.backend.has_key("pt:hk") is True
        assert self.backend.has_key("pt:nope") is False

    def test_incr_decr(self):
        self.backend.set("pt:counter", 10, timeout=60)
        assert self.backend.incr("pt:counter", 5) == 15
        assert self.backend.decr("pt:counter", 3) == 12

    def test_get_or_set_miss(self):
        result = self.backend.get_or_set("pt:gos", "computed", timeout=60)
        assert result == "computed"
        assert self.backend.get("pt:gos") == "computed"

    def test_get_or_set_hit(self):
        self.backend.set("pt:gosh", "existing", timeout=60)
        result = self.backend.get_or_set("pt:gosh", "ignored", timeout=60)
        assert result == "existing"

    def test_clear(self):
        self.backend.set("pt:cl", "data", timeout=60)
        self.backend.clear()
        assert self.backend.get("pt:cl") is None

    # ── Tag-aware API ──

    def test_set_get_with_tags(self):
        tags = [("User", "42"), ("Campaign", "7")]
        self.backend.set_with_tags("profile", {"name": "Alice"}, tags, timeout=60)
        result = self.backend.get_with_tags("profile", tags)
        assert result == {"name": "Alice"}

    def test_get_with_tags_miss(self):
        tags = [("User", "99")]
        assert self.backend.get_with_tags("missing", tags) is None
        assert self.backend.get_with_tags("missing", tags, default="fb") == "fb"

    def test_invalidation_causes_miss(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("profile", "cached", tags, timeout=60)
        assert self.backend.get_with_tags("profile", tags) == "cached"

        self.backend.invalidate_tags(tags)
        assert self.backend.get_with_tags("profile", tags) is None

    def test_partial_invalidation(self):
        """Invalidating one tag misses keys containing it but not others."""
        tag_a = [("User", "42")]
        tag_b = [("User", "99")]

        self.backend.set_with_tags("p:42", "alice", tag_a, timeout=60)
        self.backend.set_with_tags("p:99", "bob", tag_b, timeout=60)

        self.backend.invalidate_tags(tag_a)

        assert self.backend.get_with_tags("p:42", tag_a) is None  # invalidated
        assert self.backend.get_with_tags("p:99", tag_b) == "bob"  # untouched

    def test_multi_tag_invalidation(self):
        """Invalidating any one tag in a multi-tag key causes a miss."""
        tags = [("User", "42"), ("Org", "5")]
        self.backend.set_with_tags("dashboard", "data", tags, timeout=60)
        assert self.backend.get_with_tags("dashboard", tags) == "data"

        # Invalidate only one of the two tags
        self.backend.invalidate_tags([("Org", "5")])
        assert self.backend.get_with_tags("dashboard", tags) is None

    def test_delete_with_tags(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("del_me", "data", tags, timeout=60)
        self.backend.delete_with_tags("del_me", tags)
        assert self.backend.get_with_tags("del_me", tags) is None

    def test_get_or_set_with_tags_miss(self):
        tags = [("User", "42")]
        result = self.backend.get_or_set_with_tags(
            "gos_tag", "computed", tags, timeout=60
        )
        assert result == "computed"
        assert self.backend.get_with_tags("gos_tag", tags) == "computed"

    def test_get_or_set_with_tags_callable(self):
        tags = [("User", "42")]
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return "expensive"

        r1 = self.backend.get_or_set_with_tags("callable", compute, tags, timeout=60)
        assert r1 == "expensive"
        assert call_count == 1

        r2 = self.backend.get_or_set_with_tags("callable", compute, tags, timeout=60)
        assert r2 == "expensive"
        assert call_count == 1  # not called again

    def test_get_or_set_with_tags_hit(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("gos_hit", "existing", tags, timeout=60)
        result = self.backend.get_or_set_with_tags(
            "gos_hit", "ignored", tags, timeout=60
        )
        assert result == "existing"

    def test_group_id_isolation(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("stats", "weekly", tags, timeout=60, group_id="w")
        self.backend.set_with_tags("stats", "monthly", tags, timeout=60, group_id="m")

        assert self.backend.get_with_tags("stats", tags, group_id="w") == "weekly"
        assert self.backend.get_with_tags("stats", tags, group_id="m") == "monthly"

    def test_get_tag_version(self):
        version = self.backend.get_tag_version("IntUser", "1")
        assert isinstance(version, (int, float))

    def test_standard_tag_objects(self):
        """Tags can be StandardTag instances instead of tuples."""
        tags = [
            StandardTag("User", "42", handler=self.backend._handler),
        ]
        self.backend.set_with_tags("std_tag", "data", tags, timeout=60)
        assert self.backend.get_with_tags("std_tag", tags) == "data"

    def test_mixed_tag_types(self):
        """Can mix StandardTag objects and tuples."""
        tags = [
            StandardTag("User", "42", handler=self.backend._handler),
            ("Campaign", "7"),
        ]
        self.backend.set_with_tags("mixed", "data", tags, timeout=60)
        assert self.backend.get_with_tags("mixed", tags) == "data"


# ── Decorator integration against Redis ───────────────────────────────


class TestDecoratorRedis:
    """@tagged_cache and @cached_async against real Redis."""

    @pytest.fixture(autouse=True)
    def setup(self, redis_cache):
        configure_fragmented_keys(cache_name="redis", prefix="INT_DEC")
        yield
        Configuration.reset()

    def test_tagged_cache_miss_then_hit(self):
        from fragmented_keys_django.cache_utils.decorators import tagged_cache

        call_count = 0

        @tagged_cache(
            timeout=60,
            tags=["User:{user_id}"],
            vary_on=["user_id"],
            cache_name="redis",
        )
        def get_profile(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "name": "Alice"}

        r1 = get_profile(42)
        assert r1 == {"id": 42, "name": "Alice"}
        assert call_count == 1

        r2 = get_profile(42)
        assert r2 == {"id": 42, "name": "Alice"}
        assert call_count == 1  # served from cache

    def test_tagged_cache_vary_on_separates_keys(self):
        from fragmented_keys_django.cache_utils.decorators import tagged_cache

        @tagged_cache(
            timeout=60,
            tags=["User:{uid}"],
            vary_on=["uid"],
            cache_name="redis",
        )
        def get_name(uid: int):
            return f"user_{uid}"

        assert get_name(1) == "user_1"
        assert get_name(2) == "user_2"

    def test_tagged_cache_invalidation(self):
        from fragmented_keys_django.cache_utils.decorators import tagged_cache

        call_count = 0

        @tagged_cache(
            timeout=60,
            tags=["Inv:{uid}"],
            vary_on=["uid"],
            cache_name="redis",
        )
        def get_data(uid: int):
            nonlocal call_count
            call_count += 1
            return f"v{call_count}"

        assert get_data(1) == "v1"
        assert call_count == 1

        # Invalidate
        tag = StandardTag("Inv", "1")
        tag.increment()

        assert get_data(1) == "v2"  # recomputed
        assert call_count == 2

    def test_cached_async_roundtrip(self):
        import asyncio
        from fragmented_keys_django.cache_utils.decorators import cached_async

        call_count = 0

        @cached_async(
            timeout=60,
            tags=["Async:{uid}"],
            vary_on=["uid"],
            cache_name="redis",
        )
        async def get_async_data(uid: int):
            nonlocal call_count
            call_count += 1
            return {"uid": uid}

        loop = asyncio.new_event_loop()
        r1 = loop.run_until_complete(get_async_data(42))
        assert r1 == {"uid": 42}
        assert call_count == 1

        r2 = loop.run_until_complete(get_async_data(42))
        assert r2 == {"uid": 42}
        assert call_count == 1
        loop.close()


# ── ModelTagManager integration against Redis ─────────────────────────


class TestModelTagManagerRedis:
    """ModelTagManager signal-driven invalidation against real Redis."""

    @pytest.fixture(autouse=True)
    def setup(self, redis_cache):
        configure_fragmented_keys(cache_name="redis", prefix="INT_MTM")
        ModelTagManager.clear_all()
        yield
        ModelTagManager.clear_all()
        Configuration.reset()

    def test_manual_invalidation(self):
        from unittest.mock import MagicMock

        model = MagicMock()
        model.__name__ = "TestModel"

        ModelTagManager.register_model(model, auto_connect=False)

        # Set a cached value
        handler = DjangoCacheHandler("redis")
        tag = StandardTag("TestModel", "1", handler=handler)
        key = StandardKey("test_data", [tag])
        k1 = key.get_key_str(hash=True)
        handler._cache.set(k1, "cached_value", timeout=60)
        assert handler._cache.get(k1) == "cached_value"

        # Manual invalidation
        ModelTagManager.invalidate_model_tag(model, 1)

        # Key string changed — old value unreachable
        tag2 = StandardTag("TestModel", "1", handler=handler)
        key2 = StandardKey("test_data", [tag2])
        k2 = key2.get_key_str(hash=True)
        assert k1 != k2
        assert handler._cache.get(k2) is None


# ── Standalone mode against Redis ─────────────────────────────────────


class TestBackendStandaloneRedis:
    """FragmentedKeysCacheBackend in standalone mode against real Redis."""

    @pytest.fixture(autouse=True)
    def backend(self, redis_cache):
        params = {
            "LOCATION": "redis://127.0.0.1:6379/15",
            "PREFIX": "INT_SA",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
        self.backend = FragmentedKeysCacheBackend(params)
        yield
        self.backend.clear()
        Configuration.reset()

    def test_standalone_set_get(self):
        self.backend.set("sa:key", "standalone_val", timeout=60)
        assert self.backend.get("sa:key") == "standalone_val"

    def test_standalone_tag_roundtrip(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("sa:profile", "data", tags, timeout=60)
        assert self.backend.get_with_tags("sa:profile", tags) == "data"

    def test_standalone_invalidation(self):
        tags = [("User", "42")]
        self.backend.set_with_tags("sa:inv", "cached", tags, timeout=60)
        assert self.backend.get_with_tags("sa:inv", tags) == "cached"

        self.backend.invalidate_tags(tags)
        assert self.backend.get_with_tags("sa:inv", tags) is None

    def test_standalone_clear(self):
        self.backend.set("sa:cl", "data", timeout=60)
        self.backend.clear()
        assert self.backend.get("sa:cl") is None
