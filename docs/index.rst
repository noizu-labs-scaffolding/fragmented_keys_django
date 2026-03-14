fragmented-keys-django
======================

Django integration for the `fragmented-keys <https://pypi.org/project/fragmented-keys/>`_ library — tag-versioned cache invalidation where incrementing a tag version automatically invalidates all composite keys containing that tag.

**Key features:**

- Automatic cache invalidation via tag versioning — no explicit deletes
- ``@tagged_cache`` decorator for per-function caching with fine-grained tags
- ``FragmentedKeysCacheBackend`` drop-in Django cache backend
- ``ModelTagManager`` for signal-driven auto-invalidation on model save/delete
- Tag factories: ``model_tag()``, ``list_tag()``, ``aggregate_tag()``

.. toctree::
   :maxdepth: 2
   :caption: Contents

   quickstart
   usage/index
   migration
   api/index
   changelog
