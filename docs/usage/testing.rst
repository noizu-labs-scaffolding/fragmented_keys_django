Testing
=======

Setup
-----

Use ``reset_configuration()`` between tests to ensure a clean state:

.. code-block:: python

   from fragmented_keys_django.config import reset_configuration

   class CacheTestCase(TestCase):
       def setUp(self):
           reset_configuration()

Running Tests
-------------

.. code-block:: bash

   uv run pytest tests/ -v

Testing Cache Invalidation
--------------------------

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

Side-by-Side Testing
--------------------

Test that old and new cache patterns coexist:

.. code-block:: python

   def test_side_by_side_operation(self):
       cache.set("old_key", "old_value")
       self.assertEqual(cache.get("old_key"), "old_value")

       result = get_new_cached_data(42)

       # Both systems work without conflict
       self.assertEqual(cache.get("old_key"), "old_value")
