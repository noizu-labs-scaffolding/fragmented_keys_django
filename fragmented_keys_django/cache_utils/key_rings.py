"""Global KeyRing registry for defining and retrieving key templates.

Populate key rings in ``AppConfig.ready()`` alongside model registration,
then retrieve them in views to build composite cache keys from templates.

.. code-block:: python

   # In AppConfig.ready():
   from fragmented_keys_django import get_key_ring
   ring = get_key_ring("default")
   ring.define_key("org_list", ["organization", "category", "review"])

   # In views:
   ring = get_key_ring("default")
   key = ring.get_org_list_key_obj("cat:education", "__all__", "cat:education")
   cache_key = key.get_key_str()
"""

from __future__ import annotations

from fragmented_keys import FragmentedKeyRing


_rings: dict[str, FragmentedKeyRing] = {}


def register_key_ring(name: str, ring: FragmentedKeyRing) -> None:
    """Register a named key ring."""
    _rings[name] = ring


def get_key_ring(name: str = "default") -> FragmentedKeyRing:
    """Retrieve a registered key ring by name.

    :raises ValueError: If no ring is registered under *name*.
    """
    if name not in _rings:
        raise ValueError(
            f"KeyRing {name!r} not registered. "
            f"Call register_key_ring() in AppConfig.ready()."
        )
    return _rings[name]


def clear_key_rings() -> None:
    """Remove all registered key rings. For test teardowns."""
    _rings.clear()
