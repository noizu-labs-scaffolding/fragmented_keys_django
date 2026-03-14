Testing
=======

Setup
-----

Use ``reset_configuration()`` between tests to ensure a clean state. This resets
the global ``Configuration`` in the ``fragmented_keys`` library — clearing the
default cache handler and prefix so each test starts fresh.

.. code-block:: python

   from fragmented_keys_django.config import reset_configuration

   class CacheTestCase(TestCase):
       def setUp(self):
           reset_configuration()

**What happens internally:** ``reset_configuration()`` calls ``Configuration.reset()``
on the upstream ``fragmented_keys`` library, which clears the default cache handler and
global prefix. Without this, tags from one test could leak version state into another.

Running Tests
-------------

.. code-block:: bash

   uv run pytest tests/ -v

Testing Cache Invalidation
--------------------------

This test verifies the full lifecycle: cache miss → cache hit → invalidation → cache
miss again. It proves that tag versioning actually controls cache freshness.

.. code-block:: python

   from django.test import TestCase
   from fragmented_keys_django import ModelTagManager, tagged_cache

   class CacheInvalidationTest(TestCase):
       @classmethod
       def setUpClass(cls):
           super().setUpClass()
           from django.core.cache import caches
           cls.test_cache = caches["default"]

       def test_cache_invalidation(self):
           user = User.objects.create_user(username="test", id=42)

           # First call — cache miss
           result1 = self.get_user_cache(user.id)
           self.assertIsNotNone(result1)

           # Second call — cache hit
           result2 = self.get_user_cache(user.id)
           self.assertEqual(result1, result2)

           # Invalidate
           ModelTagManager.invalidate_model_tag(User, user.id)

           # Third call — cache miss (recomputed)
           result3 = self.get_user_cache(user.id)

       @tagged_cache(
           timeout=60,
           tags=["User:{user_id}"],
           vary_on=["user_id"],
       )
       def get_user_cache(self, user_id):
           return User.objects.get(pk=user_id)

**What happens internally during the test:**

1. **First call:** Tag ``User:42`` doesn't exist in the cache yet —
   ``StandardTag.get_tag_version()`` returns a default (e.g., ``0``). The key is
   composed with version ``0``, cache miss, function runs, result stored.
2. **Second call:** Same tag version (``0``), same composed key, cache hit. The
   function is *not* called — the decorator returns the cached result directly.
3. **invalidate_model_tag:** Increments ``User:42`` to version ``1`` in Redis.
4. **Third call:** Tag version is now ``1``, composed key is different from the one
   stored at version ``0``. Cache miss, function runs again.

.. admonition:: Testing tip

   Use Django's ``override_settings`` with a ``LocMemCache`` backend for fast,
   isolated tests. The fragmented keys system works with any Django cache backend —
   it doesn't require Redis for testing.

   .. code-block:: python

      @override_settings(CACHES={
          "default": {
              "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
          }
      })
      class FastCacheTest(TestCase):
          ...

Side-by-Side Testing
--------------------

When migrating from vanilla Django caching, verify that old and new cache patterns
coexist without conflict. The fragmented keys backend operates in its own key namespace,
so existing ``cache.get()``/``cache.set()`` calls are unaffected.

.. code-block:: python

   def test_side_by_side_operation(self):
       cache.set("old_key", "old_value")
       self.assertEqual(cache.get("old_key"), "old_value")

       result = get_new_cached_data(42)

       # Both systems work without conflict
       self.assertEqual(cache.get("old_key"), "old_value")

**What happens internally:** The fragmented keys system writes to the same underlying
Redis instance but uses different key strings (composed with tag versions and prefixes).
There is zero overlap between ``"old_key"`` and the tag-versioned composite key that
``get_new_cached_data`` produces. They coexist in the same Redis database without
interfering.

Testing ModelTagManager
-----------------------

When testing models registered with ``ModelTagManager``, be aware that signal handlers
persist across tests unless explicitly cleared. Use ``clear_all()`` in test teardowns
to prevent signal leakage.

.. code-block:: python

   class ModelTagTest(TestCase):
       def setUp(self):
           from fragmented_keys_django.config import reset_configuration
           reset_configuration()
           ModelTagManager.clear_all()

           # Re-register only what this test needs
           ModelTagManager.register_model(User)

       def tearDown(self):
           ModelTagManager.clear_all()

       def test_auto_invalidation(self):
           user = User.objects.create_user(username="test", id=1)

           # Cache something tagged with User:1
           result1 = get_cached_user_data(user.id)

           # Trigger auto-invalidation via save
           user.username = "updated"
           user.save()  # post_save fires → User:1 tag incremented

           # Cache should miss now
           result2 = get_cached_user_data(user.id)

**What happens internally:**

1. ``clear_all()`` disconnects all ``post_save``/``post_delete`` signal handlers and
   empties ``_registered_models``. This prevents handlers registered in other tests
   from firing unexpectedly.
2. ``register_model(User)`` reconnects fresh handlers for this test only.
3. When ``user.save()`` runs, the ``post_save`` signal fires, ``_on_model_change``
   increments ``User:1``, and the next cache lookup misses.
4. ``tearDown`` cleans up again so subsequent tests start clean.
