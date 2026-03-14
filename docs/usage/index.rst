Usage Guide
===========

fragmented-keys-django supports two usage modes. Choose based on your needs,
or mix both in the same project.

- **Decorator mode** — Wrap individual functions with ``@tagged_cache``. Best for
  view helpers, service functions, and anywhere you have a clear compute-and-cache
  pattern. Start here if you're adopting fragmented keys for the first time.

- **Backend mode** — Use ``FragmentedKeysCacheBackend`` as a Django cache backend and
  call ``*_with_tags`` methods directly. Best for management commands, services, or
  places where a decorator doesn't fit.

Both modes share the same tag versioning system. A tag incremented by a model save
invalidates caches in both modes simultaneously.

.. toctree::
   :maxdepth: 2

   decorator
   backend
   tags
   testing
