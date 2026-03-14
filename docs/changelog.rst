Changelog
=========

0.1.0 (2024)
-------------

- Initial release
- ``DjangoCacheHandler`` protocol adapter
- ``FragmentedKeysCacheBackend`` with tag-aware API (``*_with_tags``, ``invalidate_tags``)
- ``@tagged_cache`` and ``@cached_async`` decorators
- ``ModelTagManager`` with signal-driven auto-invalidation
- Tag factories: ``model_tag()``, ``list_tag()``, ``aggregate_tag()``, ``custom_tag()``
- ``configure_fragmented_keys()`` one-call setup
