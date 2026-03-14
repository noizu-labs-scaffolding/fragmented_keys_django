Tags & Model Helpers
====================

Tag Factories
-------------

Tag factories are semantic aliases — they all create a ``StandardTag`` under the hood.
The different names exist to make your code's *intent* clear to future readers. There
is no behavioral difference between them.

.. code-block:: python

   from fragmented_keys_django import model_tag, list_tag, aggregate_tag
   from fragmented_keys_django.cache_utils.tags import custom_tag

   # Model instance tag
   user_tag = model_tag("User", str(user_id))

   # List/collection tag
   donations_tag = list_tag("Donations", str(user_id))

   # Aggregate/statistics tag
   stats_tag = aggregate_tag("DailyStats", f"{user_id}_{date}")

   # Custom tag
   weather_tag = custom_tag("Weather", f"{city}_{date}")

**What happens internally:** Every factory function calls
``StandardTag(name, str(instance_id))`` and returns it. That's it — they're one-liners
in ``tags.py``. The semantic names help you communicate intent:

- ``model_tag`` → "this cache depends on a specific model instance"
- ``list_tag`` → "this cache holds a collection scoped to an owner"
- ``aggregate_tag`` → "this cache holds computed statistics/rollups"
- ``custom_tag`` → "this doesn't fit the other categories"

**When to use which:** Choose the one that best describes your cache's relationship
to the data. Future readers will understand *why* a cache is tagged just from the
factory name.

Using Tags with StandardKey
---------------------------

This is the manual cache pattern — create tags, compose a key, do the get-or-compute
yourself. Use this when a decorator doesn't fit (management commands, services, Celery
tasks, or conditional caching logic).

.. code-block:: python

   from fragmented_keys import StandardKey
   from fragmented_keys_django import model_tag, list_tag
   from django.core.cache import cache

   user_tag = model_tag("User", str(user_id))
   donations_tag = list_tag("Donations", str(user_id))

   key = StandardKey("UserDashboard", [user_tag, donations_tag])
   cache_key = key.get_key_str()

   result = cache.get(cache_key)
   if result is None:
       result = compute_dashboard()
       cache.set(cache_key, result, timeout=3600)

**What happens internally:**

1. ``model_tag("User", "42")`` returns ``StandardTag("User", "42")``.
   ``list_tag("Donations", "42")`` returns ``StandardTag("Donations", "42")``.
2. ``StandardKey("UserDashboard", [user_tag, donations_tag])`` creates a composite key
   object holding a base name and a list of tags.
3. ``key.get_key_str()`` queries Redis for the current version of each tag, then combines
   ``base_name + tag_name + instance + version`` for each tag into a single deterministic
   string. This is the actual Redis key you'll use with ``cache.get()``.
4. If either ``User:42`` or ``Donations:42`` is incremented, ``get_key_str()`` produces
   a different string → cache miss.

**This is exactly what** ``@tagged_cache`` **does internally** — the same flow in
``decorators.py`` lines 66–99, just without the decorator sugar.

Composite Key Helper
--------------------

A convenience function that combines tag creation and key name construction in one call,
reducing boilerplate when you have multiple tags and vary parameters.

.. code-block:: python

   from fragmented_keys import StandardKey
   from fragmented_keys_django.cache_utils.tags import build_composite_key

   tag_objs, key_name = build_composite_key(
       base_name="UserProfile",
       tags=[("User", "42")],
       vary_params=[("include_history", "true")],
   )

   key = StandardKey(key_name, tag_objs)
   cache_key = key.get_key_str()

**What happens internally:**

1. ``build_composite_key`` iterates the ``tags`` list, creating
   ``StandardTag(name, instance)`` for each tuple.
2. It builds the key name by appending vary params:
   ``"UserProfile"`` + ``"_include_history_true"`` → ``"UserProfile_include_history_true"``.
3. Returns the tag objects and composed key name as a tuple — you still need to create
   the ``StandardKey`` and call ``get_key_str()`` yourself.
4. This is the same logic the ``@tagged_cache`` decorator uses internally, exposed as
   a standalone function for use outside decorators.

ModelTagManager
---------------

Register Django models for automatic cache invalidation via ``post_save`` and
``post_delete`` signals. When a registered model instance is saved or deleted, its
corresponding tag version is incremented automatically.

.. code-block:: python

   from fragmented_keys_django import ModelTagManager
   from django.contrib.auth.models import User
   from myapp.models import Donation, Campaign

   # Register with default tag name (model class name)
   ModelTagManager.register_model(User)          # Tag: User:{pk}
   ModelTagManager.register_model(Donation)       # Tag: Donation:{pk}

   # Register with custom tag name
   ModelTagManager.register_model(Campaign, tag_name="Campaign")

**What happens internally:**

1. For each ``register_model()`` call, the model class is stored as a key in
   ``ModelTagManager._registered_models`` with the tag name as the value. The default
   tag name is ``model.__name__`` (e.g., ``"User"``).
2. ``connect_signals()`` disconnects any existing handlers first (to prevent duplicate
   registrations if ``ready()`` runs twice), then connects fresh ``post_save`` and
   ``post_delete`` handlers with ``weak=False``.
3. When ``Donation(pk=7).save()`` fires, Django emits ``post_save`` with
   ``sender=Donation``. The handler ``_on_model_change`` looks up ``Donation`` in
   ``_registered_models`` → finds ``"Donation"``, creates ``StandardTag("Donation", "7")``
   and calls ``.increment()``.
4. **Scope is per-instance.** Only ``Donation:7`` is incremented. Caches tagged with
   ``Donation:3`` or ``Donation:99`` are untouched.

.. admonition:: Important

   The ``tag_name`` you register with must match the tag names in your
   ``@tagged_cache`` decorators. If you register ``Campaign`` with
   ``tag_name="Campaign"``, your decorators must use ``tags=["Campaign:{id}"]`` —
   not ``"campaign:{id}"`` or any other casing.

Manual Invalidation
^^^^^^^^^^^^^^^^^^^

Use manual invalidation for changes that bypass Django's ORM — bulk SQL updates,
raw queries, external webhooks, management commands, or Celery tasks that modify data
without calling ``model.save()``.

.. code-block:: python

   # Invalidate by model class
   ModelTagManager.invalidate_model_tag(User, 42)

   # Invalidate by model name string
   ModelTagManager.invalidate_model_tag("User", 42)

**What happens internally:**

1. ``invalidate_model_tag(User, 42)`` looks up the tag name for ``User`` in
   ``_registered_models`` → ``"User"``, creates ``StandardTag("User", "42")``, and
   calls ``.increment()``.
2. The string overload (``"User"``) iterates ``_registered_models`` to find a model
   whose ``__name__`` matches, then does the same thing.
3. Returns ``True`` on success, ``False`` if the model isn't registered or an error occurs.
4. This does the same thing the ``post_save`` signal handler does — it's just for
   situations where no signal fires.

Introspection
^^^^^^^^^^^^^

.. code-block:: python

   ModelTagManager.is_registered(User)         # True/False
   ModelTagManager.get_registered_models()     # {User: "User", ...}
   ModelTagManager.get_tag_name_for_model(User)  # "User"

**What happens internally:**

- ``is_registered`` checks if the model class exists in ``_registered_models`` (a dict lookup).
- ``get_registered_models`` returns a *copy* of ``_registered_models`` (so you can't
  accidentally mutate the registry).
- ``get_tag_name_for_model`` first tries a direct dict lookup, then falls back to
  ``django.apps.apps.get_model()`` for ``"app_label.ModelName"`` style lookups.

Unregistering
^^^^^^^^^^^^^

.. code-block:: python

   ModelTagManager.unregister_model(User)
   ModelTagManager.clear_all()  # Unregister everything

**What happens internally:**

- ``unregister_model`` disconnects the ``post_save``/``post_delete`` signals for that model
  and removes it from ``_registered_models``. Future saves of that model will *not*
  increment any tags.
- ``clear_all`` iterates all registered models and calls ``unregister_model`` on each.
  Useful in test teardowns to ensure a clean state.
