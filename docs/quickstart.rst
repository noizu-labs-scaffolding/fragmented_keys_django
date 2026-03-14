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

The fragmented cache backend sits *on top of* your existing cache. It doesn't
replace Redis or Memcached — it uses your existing backend for storage while
adding tag-versioned key composition on the read/write path.

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

**What happens internally:**

1. ``FragmentedKeysCacheBackend.__init__()`` reads ``CACHE_NAME`` and creates a
   ``DjangoCacheHandler`` that wraps your ``"default"`` cache. The handler adapts
   Django's cache API (arbitrary Python objects) to the ``fragmented_keys.CacheHandler``
   protocol (string-based).
2. ``PREFIX`` is passed to ``Configuration.set_global_prefix()`` — it namespaces all
   tag version keys in Redis so multiple apps sharing the same Redis instance don't
   collide.
3. Your existing ``"default"`` cache continues to work normally. The ``"fragmented"``
   backend is additive — you can adopt it incrementally alongside existing cache calls.

Register Models for Auto-Invalidation
--------------------------------------

This is where you wire up the library at Django startup. ``AppConfig.ready()``
runs once after all apps are loaded, making it the right place for signal
registration and global configuration.

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

**What happens internally:**

1. ``configure_fragmented_keys()`` creates a ``DjangoCacheHandler`` and calls
   ``Configuration.set_default_cache_handler()`` — this means any ``StandardTag``
   or ``StandardKey`` created later will automatically use your Django cache for
   version storage without needing to pass a handler explicitly.
2. ``ModelTagManager.register_model(User)`` stores the mapping
   ``User → "User"`` in ``_registered_models`` and calls ``connect_signals(User)``,
   which hooks ``post_save`` and ``post_delete`` signals with ``weak=False``
   (so the handler isn't garbage collected).
3. ``register_model(MyModel, tag_name="CustomName")`` maps ``MyModel → "CustomName"``.
   Your ``@tagged_cache`` tags must use ``tags=["CustomName:{param}"]`` to link up —
   not ``"MyModel:{param}"``.
4. From this point on, ``User.save()`` or ``User.objects.get(pk=42).delete()`` triggers
   ``_on_model_change``, which calls ``StandardTag("User", "42").increment()``.

Use the ``@tagged_cache`` Decorator
------------------------------------

The decorator is the primary API for most use cases. It wraps a function with
tag-based caching: build a composite cache key from tag versions + function
arguments, check the cache, and only call the function on a miss.

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

**What happens internally when called with** ``user_id=42, filter_type="weekly"``:

1. **Tag resolution:** For ``"Dashboard"`` (no placeholder), a ``StandardTag("Dashboard", "")``
   is created. For ``"User:{user_id}"``, the decorator uses ``inspect.signature(func)`` to
   find that ``user_id`` is at parameter index 0, reads ``args[0] = 42``, and creates
   ``StandardTag("User", "42")``.
2. **Key name:** The base key is ``"myapp.views.get_dashboard_statistics"``. Since
   ``vary_on=["user_id", "filter_type"]``, the decorator appends
   ``_user_id_42_filter_type_weekly``.
3. **Key composition:** ``StandardKey(base_key_name, [dashboard_tag, user_tag]).get_key_str()``
   queries Redis for each tag's current version and produces a deterministic key string
   embedding those versions.
4. **Cache lookup:** ``cache.get(cache_key)`` — if hit, return immediately; if miss,
   call the function, store with ``cache.set(cache_key, result, timeout=3600)``.

**When** ``User(pk=42)`` **is saved:** ``ModelTagManager`` increments ``User:42``'s version.
Next call with ``user_id=42`` composes a different key string → automatic cache miss →
recomputation. Calls with ``user_id=7`` are unaffected because ``User:7``'s version
hasn't changed.

**No explicit** ``cache.delete()`` **needed.** The old entry (keyed with the previous
version) is still in Redis but unreachable — it expires naturally via the 1-hour TTL.

How It Works
------------

Cache keys embed current tag versions. When a model changes:

1. ``ModelTagManager`` receives ``post_save``/``post_delete`` signal
2. Calls ``StandardTag.increment()`` to bump the tag version in Redis
3. Next cache read composes a different key string (because version changed)
4. Cache miss → recompute → store under new key
5. Old entries expire naturally via TTL

No explicit ``cache.delete()`` calls needed.

This is fundamentally different from traditional invalidation where you must track
and delete every key. With fragmented keys, you never delete — you just make old
keys unreachable by incrementing a version number. The old entries become orphans
that expire via their original TTL.
