Backend Mode
============

``FragmentedKeysCacheBackend`` is a drop-in Django ``BaseCache`` subclass that adds tag-aware caching methods on top of the standard Django cache API.

Configuration
-------------

.. code-block:: python

   # settings.py
   CACHES = {
       "default": {
           "BACKEND": "django_redis.cache.RedisCache",
           "LOCATION": "redis://127.0.0.1:6379/1",
       },
       "fragmented": {
           "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
           "CACHE_NAME": "default",   # Underlying cache to use
           "PREFIX": "NOZ_FRAG",      # Global tag prefix
       },
   }

Standard Django API
-------------------

All standard ``BaseCache`` methods work as expected:

.. code-block:: python

   from django.core.cache import caches

   cache = caches["fragmented"]

   cache.set("my_key", data, timeout=3600)
   data = cache.get("my_key")
   cache.delete("my_key")

Tag-Aware API
-------------

The backend exposes ``*_with_tags`` methods for tag-based caching:

.. code-block:: python

   from django.core.cache import caches

   frag = caches["fragmented"]

   # Set with tags (tuples or StandardTag objects)
   frag.set_with_tags("user_profile", profile_data, [("User", "42")], timeout=3600)

   # Get with tags
   data = frag.get_with_tags("user_profile", [("User", "42")], default=None)

   # Get-or-set (default can be a callable)
   data = frag.get_or_set_with_tags(
       "user_profile",
       lambda: expensive_query(42),
       [("User", "42")],
       timeout=3600,
   )

   # Delete a specific tagged entry
   frag.delete_with_tags("user_profile", [("User", "42")])

   # Invalidate all entries depending on these tags
   frag.invalidate_tags([("User", "42")])

Tags can be ``(name, instance)`` tuples, ``StandardTag`` objects, or a mix of both.

Group IDs
---------

Use ``group_id`` to namespace keys that share the same base name and tags:

.. code-block:: python

   frag.set_with_tags("stats", weekly_data, tags, group_id="weekly")
   frag.set_with_tags("stats", monthly_data, tags, group_id="monthly")

Introspection
-------------

.. code-block:: python

   # Check current tag version (useful for debugging)
   version = frag.get_tag_version("User", "42")

   # Create a FragmentedKeyRing pre-configured with this backend
   ring = frag.create_key_ring()
