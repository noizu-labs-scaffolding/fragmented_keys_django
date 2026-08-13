"""Regression tests for the single-namespace fix and the global cache epoch.

Both exist because of the same incident: tags built outside the cache backend
stored their versions at ``:1::1:<tag>`` while the backend's own ``*_with_tags``
API used ``:1:<tag>``, so the two could not invalidate each other. Fixing the
naming merges the namespaces; raising the epoch strands the entries that were
written while they were split.
"""

from unittest.mock import MagicMock, patch

import pytest

from fragmented_keys import Configuration, MemoryHandler, StandardKey, StandardTag
from fragmented_keys_django.cache_backends.django_backend import (
    FragmentedKeysCacheBackend,
)
from fragmented_keys_django.cache_utils.epoch import (
    DEFAULT_EPOCH,
    EPOCH_TAG_INSTANCE,
    EPOCH_TAG_NAME,
    epoch_tag,
    get_cache_epoch,
    is_epoch_tag,
    set_cache_epoch,
    with_epoch,
)


@pytest.fixture(autouse=True)
def _reset_epoch():
    yield
    set_cache_epoch(DEFAULT_EPOCH)


@pytest.fixture
def handler():
    h = MemoryHandler()
    Configuration.reset()
    Configuration.set_default_cache_handler(h)
    Configuration.set_global_prefix("GNP")
    yield h
    Configuration.reset()


# ── the namespace fix ────────────────────────────────────────────────────────


def _backend_with_mock_cache():
    """Build a backend whose wrapped cache is a mock, so calls can be asserted."""
    mock_cache = MagicMock()
    with patch("django.core.cache.caches") as mock_caches, patch(
        "fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler"
    ) as mock_handler_class:
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler
        backend = FragmentedKeysCacheBackend("", {"CACHE_NAME": "default", "PREFIX": "GNP"})
    return backend, mock_cache


@pytest.mark.parametrize(
    "call, expect_method, expect_args",
    [
        (lambda b: b.get("k"), "get", (("k",), {"version": None})),
        (lambda b: b.set("k", "v"), "set", (("k", "v"), {"timeout": None, "version": None})),
        (lambda b: b.delete("k"), "delete", (("k",), {"version": None})),
        (lambda b: b.has_key("k"), "has_key", (("k",), {"version": None})),
        (lambda b: b.delete_many(["k"]), "delete_many", ((["k"],), {"version": None})),
    ],
)
def test_passthrough_does_not_prefix_the_key(call, expect_method, expect_args):
    """The wrapped backend must receive the caller's key verbatim.

    Pre-fix these methods applied ``self.make_key()`` first, so the wrapped
    backend prefixed an already-prefixed key.
    """
    backend, mock_cache = _backend_with_mock_cache()
    call(backend)

    args, kwargs = expect_args
    getattr(mock_cache, expect_method).assert_called_once_with(*args, **kwargs)

    # Belt and braces: nothing handed downstream may carry a ":1:" prefix.
    passed = getattr(mock_cache, expect_method).call_args
    flat = [a for a in passed.args if isinstance(a, str)]
    flat += [x for a in passed.args if isinstance(a, list) for x in a]
    for value in flat:
        assert not value.startswith(":"), f"{expect_method} pre-prefixed the key: {value!r}"


def test_tag_versions_land_in_one_namespace(handler):
    """A tag built by the backend and one built bare must agree.

    This is the defect in miniature: before the fix these two paths wrote to
    different Redis keys and held different versions for the same logical tag.
    """
    backend, _ = _backend_with_mock_cache()

    from_backend = backend._normalize_tags([("Page", "careers")])[0]
    bare = StandardTag("Page", "careers")

    assert from_backend.get_tag_name() == bare.get_tag_name() == "Page_careersGNP"


# ── the global epoch ─────────────────────────────────────────────────────────


def test_epoch_tag_shape(handler):
    t = epoch_tag()
    assert t.get_tag_name() == f"{EPOCH_TAG_NAME}_{EPOCH_TAG_INSTANCE}GNP"
    assert t.get_tag_version() == DEFAULT_EPOCH
    # Constant: never queried in bulk, never mutated.
    assert t.delegate_cache_query("MemoryHandler") is False
    t.increment()
    assert t.get_tag_version() == DEFAULT_EPOCH


def test_with_epoch_prepends_and_is_idempotent(handler):
    tags = [StandardTag("Page", "careers")]

    once = with_epoch(tags)
    assert len(once) == 2
    assert is_epoch_tag(once[0]), "the epoch must be first — tag order is part of the key"

    twice = with_epoch(once)
    assert twice is once or len(twice) == 2, "with_epoch must not stack duplicate epochs"


def test_raising_the_epoch_changes_every_key(handler):
    """The point of the epoch: one value change strands the whole cache."""
    tags = [StandardTag("Page", "careers", version=1.0)]

    set_cache_epoch(1.0)
    before = StandardKey("content_page", with_epoch(tags)).get_key_str()

    set_cache_epoch(2.0)
    after = StandardKey(
        "content_page", with_epoch([StandardTag("Page", "careers", version=1.0)])
    ).get_key_str()

    assert before != after, "raising the epoch did not change the composite key"
    assert get_cache_epoch() == 2.0


def test_epoch_isolates_pre_fix_entries(handler):
    """A key built without the epoch must never collide with one built with it.

    That is what makes the epoch a safe cutover mechanism for the stage-to-prod
    push: entries written by the pre-fix build stay unreachable rather than
    being reinterpreted under the merged namespace.
    """
    tags = [StandardTag("Page", "careers", version=1.0)]
    pre_fix = StandardKey("content_page", tags).get_key_str()
    post_fix = StandardKey("content_page", with_epoch(tags)).get_key_str()
    assert pre_fix != post_fix


def test_backend_reads_epoch_from_settings():
    mock_cache = MagicMock()
    with patch("django.core.cache.caches") as mock_caches, patch(
        "fragmented_keys_django.cache_backends.handlers.DjangoCacheHandler"
    ) as mock_handler_class:
        mock_caches.__getitem__.return_value = mock_cache
        mock_handler = MagicMock()
        mock_handler._cache = mock_cache
        mock_handler_class.return_value = mock_handler
        FragmentedKeysCacheBackend(
            "", {"CACHE_NAME": "default", "PREFIX": "GNP", "EPOCH": 7.0}
        )
    assert get_cache_epoch() == 7.0


def test_configure_sets_epoch(handler):
    from fragmented_keys_django import configure_fragmented_keys

    configure_fragmented_keys(cache_name="default", prefix="GNP", epoch=3.0,
                              setup_key_ring=False)
    assert get_cache_epoch() == 3.0


def test_backend_keys_carry_the_epoch(handler):
    """A key built through the backend must include the epoch dimension."""
    backend, _ = _backend_with_mock_cache()

    set_cache_epoch(1.0)
    k1 = backend._build_tagged_key("content_page", [("Page", "careers")])
    set_cache_epoch(2.0)
    k2 = backend._build_tagged_key("content_page", [("Page", "careers")])

    assert k1 != k2, "backend-built keys do not carry the epoch"
