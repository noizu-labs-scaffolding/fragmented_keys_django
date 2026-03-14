Tags & Model Helpers
====================

Tag Factories
-------------

Convenience functions for creating ``StandardTag`` instances:

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

Using Tags with StandardKey
---------------------------

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

Composite Key Helper
--------------------

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

ModelTagManager
---------------

Register Django models for automatic cache invalidation via ``post_save`` and ``post_delete`` signals:

.. code-block:: python

   from fragmented_keys_django import ModelTagManager
   from django.contrib.auth.models import User
   from myapp.models import Donation, Campaign

   # Register with default tag name (model class name)
   ModelTagManager.register_model(User)          # Tag: User:{pk}
   ModelTagManager.register_model(Donation)       # Tag: Donation:{pk}

   # Register with custom tag name
   ModelTagManager.register_model(Campaign, tag_name="Campaign")

Manual Invalidation
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # Invalidate by model class
   ModelTagManager.invalidate_model_tag(User, 42)

   # Invalidate by model name string
   ModelTagManager.invalidate_model_tag("User", 42)

Introspection
^^^^^^^^^^^^^

.. code-block:: python

   ModelTagManager.is_registered(User)         # True/False
   ModelTagManager.get_registered_models()     # {User: "User", ...}
   ModelTagManager.get_tag_name_for_model(User)  # "User"

Unregistering
^^^^^^^^^^^^^

.. code-block:: python

   ModelTagManager.unregister_model(User)
   ModelTagManager.clear_all()  # Unregister everything
