"""Tests for the KeyRing registry."""

import pytest

from fragmented_keys import FragmentedKeyRing

from fragmented_keys_django.cache_utils.key_rings import (
    register_key_ring,
    get_key_ring,
    clear_key_rings,
)


@pytest.fixture(autouse=True)
def clean_rings():
    clear_key_rings()
    yield
    clear_key_rings()


class TestKeyRingRegistry:
    def test_register_and_get(self):
        ring = FragmentedKeyRing()
        register_key_ring("test", ring)

        assert get_key_ring("test") is ring

    def test_get_unregistered_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            get_key_ring("nonexistent")

    def test_clear_key_rings(self):
        register_key_ring("a", FragmentedKeyRing())
        register_key_ring("b", FragmentedKeyRing())
        clear_key_rings()

        with pytest.raises(ValueError):
            get_key_ring("a")

    def test_overwrite_existing(self):
        ring1 = FragmentedKeyRing()
        ring2 = FragmentedKeyRing()
        register_key_ring("test", ring1)
        register_key_ring("test", ring2)

        assert get_key_ring("test") is ring2
