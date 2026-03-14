Backend Mode
============

``FragmentedKeysCacheBackend`` is a drop-in Django ``BaseCache`` subclass that adds
tag-aware caching methods on top of the standard Django cache API. It wraps any other
Django cache backend (Redis, Memcached, etc.) and provides ``*_with_tags`` methods
for tag-versioned key composition.

Use this mode when you need direct control over cache operations — in management
commands, service classes, Celery tasks, or anywhere a decorator doesn't fit.

Configuration
-------------

The fragmented backend sits on top of your existing cache. ``CACHE_NAME`` tells it
which underlying Django cache to use for actual storage; ``PREFIX`` namespaces tag
version keys to avoid collisions between apps sharing the same Redis instance.

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

**What happens internally:**

1. ``FragmentedKeysCacheBackend.__init__()`` reads ``CACHE_NAME`` ("default") and
   creates a ``DjangoCacheHandler`` wrapping ``caches["default"]``.
2. The handler implements the ``fragmented_keys.CacheHandler`` protocol — it translates
   between Django's cache API (which stores/returns arbitrary Python objects) and the
   fragmented_keys library (which works with strings).
3. ``Configuration.set_default_cache_handler(handler)`` is called, so any ``StandardTag``
   or ``StandardKey`` created elsewhere in your app automatically uses this handler.
4. ``Configuration.set_global_prefix("NOZ_FRAG")`` prefixes all tag version keys —
   e.g., a tag stored in Redis might look like ``NOZ_FRAG:tag:User:42``.

Standard Django API
-------------------

All standard ``BaseCache`` methods work as expected. These pass through to the underlying
cache without any tag composition — they behave identically to using the underlying
cache directly.

.. code-block:: python

   from django.core.cache import caches

   cache = caches["fragmented"]

   cache.set("my_key", data, timeout=3600)
   data = cache.get("my_key")
   cache.delete("my_key")

**What happens internally:** Each method calls ``self.make_key(key, version)`` (Django's
built-in key prefixing), then delegates to ``self._handler._cache`` — which is the
underlying ``"default"`` cache. No tag composition occurs. This ensures the backend is
fully compatible with code that doesn't use tags.

Tag-Aware API
-------------

The ``*_with_tags`` methods are where the fragmented key magic happens. These methods
compose cache keys from a base name + tag versions, so the key automatically changes
when any tag is incremented.

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

**What happens internally:**

1. ``_normalize_tags()`` converts your input into ``StandardTag`` objects. ``(name, instance)``
   tuples become ``StandardTag(str(name), str(instance), handler=self._handler)``.
   ``StandardTag`` instances are passed through as-is.
2. ``_build_tagged_key()`` creates a ``StandardKey(key, tag_objs)`` and calls
   ``get_key_str(hash=True)`` — this queries Redis for each tag's current version,
   combines them with the base key name, and hashes the result into a fixed-length
   cache key string.
3. ``set_with_tags`` stores the value under this composite key. ``get_with_tags`` looks
   it up. If any tag version has changed since the value was stored, the composite key
   differs and you get a cache miss — the old entry is unreachable.
4. ``invalidate_tags`` doesn't delete anything — it calls ``tag.increment()`` on each
   tag, bumping their version counters. All future lookups using those tags will compose
   different key strings.

Tags can be ``(name, instance)`` tuples, ``StandardTag`` objects, or a mix of both.

**get_or_set_with_tags — callable default:** When ``default`` is a callable (like a lambda),
it is only called on cache miss. This avoids running expensive queries when the cache
already has the value.

Group IDs
---------

Use ``group_id`` to namespace keys that share the same base name and tags but represent
different data (e.g., different time ranges of the same metric).

.. code-block:: python

   frag.set_with_tags("stats", weekly_data, tags, group_id="weekly")
   frag.set_with_tags("stats", monthly_data, tags, group_id="monthly")

**What happens internally:** The ``group_id`` is passed to ``StandardKey(..., group_id="weekly")``,
which includes it in the key composition. This ensures ``stats + tags + "weekly"`` and
``stats + tags + "monthly"`` resolve to different cache keys, even though they share the
same base name and tags.

When any of the shared tags are incremented, *both* entries become stale simultaneously —
the group_id provides separation, not independent invalidation.

Introspection
-------------

Useful for debugging cache behavior — check what version a tag is at, or create a
pre-configured ``FragmentedKeyRing`` for advanced usage.

.. code-block:: python

   # Check current tag version (useful for debugging)
   version = frag.get_tag_version("User", "42")

   # Create a FragmentedKeyRing pre-configured with this backend
   ring = frag.create_key_ring()

**What happens internally:**

- ``get_tag_version`` creates a ``StandardTag("User", "42", handler=self._handler)``
  and calls ``get_tag_version()`` — reading the version counter directly from Redis.
  Returns a ``float`` (the version number).
- ``create_key_ring`` creates a ``FragmentedKeyRing`` with the backend's handler and
  prefix pre-configured, saving you from passing those in manually. The ``KeyRing`` is
  from the upstream ``fragmented_keys`` library and is useful for managing multiple
  related keys as a group.
