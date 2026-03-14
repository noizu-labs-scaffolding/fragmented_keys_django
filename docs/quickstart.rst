Quick Start
===========

Installation
------------

The package is included in the project as a local package:

.. code-block:: bash

   pip install fragmented-keys
   pip install -e ./fragmented_keys_django

Or add to ``requirements.txt``:

.. code-block:: text

   fragmented-keys>=0.1.3
   -e ./fragmented_keys_django

Configure Django Settings
-------------------------

Add the fragmented cache backend to your ``settings.py``:

.. code-block:: python

   CACHES = {
       "default": {
           "BACKEND": "django_redis.cache.RedisCache",
           "LOCATION": "redis://127.0.0.1:6379/1",
       },
       "fragmented": {
           "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
           "CACHE_NAME": "default",
           "PREFIX": "NOZ_FRAG",
       },
   }

Register Models for Auto-Invalidation
--------------------------------------

In your app's ``AppConfig.ready()``:

.. code-block:: python

   from django.apps import AppConfig

   class MyAppConfig(AppConfig):
       name = "myapp"

       def ready(self):
           from fragmented_keys_django import configure_fragmented_keys, ModelTagManager
           from django.contrib.auth.models import User
           from myapp.models import MyModel

           configure_fragmented_keys(cache_name="default", prefix="NOZ")

           ModelTagManager.register_model(User)
           ModelTagManager.register_model(MyModel, tag_name="CustomName")

Use the ``@tagged_cache`` Decorator
------------------------------------

.. code-block:: python

   from fragmented_keys_django import tagged_cache

   @tagged_cache(
       timeout=3600,
       tags=["Dashboard", "User:{user_id}"],
       vary_on=["user_id", "filter_type"],
   )
   def get_dashboard_statistics(user_id: int, filter_type: str):
       data = fetch_from_database(user_id, filter_type)
       return data

When ``User`` with ``user_id=42`` is saved, the tag version increments and the cache key resolves to a new string — automatic cache miss, automatic recomputation.

How It Works
------------

Cache keys embed current tag versions. When a model changes:

1. ``ModelTagManager`` receives ``post_save``/``post_delete`` signal
2. Calls ``StandardTag.increment()`` to bump the tag version
3. Next cache read composes a different key string (because version changed)
4. Cache miss → recompute → store under new key
5. Old entries expire naturally via TTL

No explicit ``cache.delete()`` calls needed.
