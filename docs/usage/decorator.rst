Decorator Mode
==============

The ``@tagged_cache`` decorator wraps individual functions with tag-based caching.
It builds a composite cache key from the function's tag versions and arguments,
checks the cache, and only executes the function on a miss.

Basic Example
-------------

The simplest use case: cache an expensive computation and tie its invalidation
to a global tag. When the tag version changes, the cache automatically misses
without any explicit delete.

.. code-block:: python

   from fragmented_keys_django import tagged_cache

   @tagged_cache(
       timeout=3600,
       tags=["Dashboard"],
   )
   def get_dashboard_stats():
       return Stats.objects.aggregate(total=Sum("amount"))

**What happens internally — first call:**

1. The decorator wrapper in ``decorators.py`` runs.
2. **Tag resolution:** For ``"Dashboard"`` (no ``{placeholder}``), ``parse_tag_template``
   returns ``("Dashboard", "")``. ``resolve_tag_instance`` returns ``""``. A
   ``StandardTag("Dashboard", "")`` is created.
3. **Key name:** Since no ``key_name`` was passed, the decorator uses
   ``f"{func.__module__}.{func.__qualname__}"`` — e.g.,
   ``"myapp.views.get_dashboard_stats"``. No ``vary_on`` params, so nothing is appended.
4. **Key composition:** ``StandardKey("myapp.views.get_dashboard_stats", [dashboard_tag]).get_key_str()``
   queries Redis for ``Dashboard``'s current version (say, ``1``), then produces a
   deterministic key string embedding that version.
5. **Cache lookup:** ``cache.get(cache_key)`` → ``None`` (miss). The function runs,
   result is stored with ``cache.set(cache_key, result, timeout=3600)``.

**What happens on subsequent calls:** Same tag version → same key string → cache hit.
Function is *not* called.

**What happens on invalidation:** ``StandardTag("Dashboard").increment()`` bumps the
version to ``2``. Next call composes a key with version ``2`` — different string, cache
miss, function re-executes. The old entry (version ``1``) is never deleted; it expires
via TTL.

User-Specific Tags
------------------

This pattern caches per-user results. The ``{user_id}`` placeholder in the tag template
is resolved from the function's arguments, so each user gets their own cache entry *and*
their own invalidation scope.

Tag templates use ``{placeholder}`` syntax to extract values from function arguments:

.. code-block:: python

   @tagged_cache(
       timeout=1800,
       tags=["User:{user_id}"],
       vary_on=["user_id"],
   )
   def get_user_dashboard(user_id: int):
       return Dashboard.objects.filter(user_id=user_id).first()

**What happens internally when called with** ``user_id=42``:

1. **Tag resolution:** ``parse_tag_template("User:{user_id}")`` returns
   ``("User", "{user_id}")``. The decorator uses ``inspect.signature(func)`` to map
   ``user_id`` to positional index 0, reads ``args[0] = 42``, and creates
   ``StandardTag("User", "42")``.
2. **Key name with vary_on:** The base key is ``"myapp.views.get_user_dashboard"``.
   Since ``vary_on=["user_id"]``, the decorator appends ``_user_id_42``.
3. **Key composition:** ``StandardKey`` looks up ``User:42``'s version in Redis and
   embeds it in the key string.
4. **Cache hit/miss:** Standard get-or-compute flow.

**When** ``User(pk=42).save()`` **fires:** ``ModelTagManager._on_model_change`` increments
``User:42``'s version. Next call to ``get_user_dashboard(42)`` composes a different key
→ miss → recompute. Meanwhile, ``get_user_dashboard(7)`` still hits its cache because
``User:7`` hasn't changed.

Multiple Tags
-------------

When a cache entry depends on multiple entities, list all relevant tags. The cache
invalidates when *any* of the tags change — changing either one produces a different
composite key.

.. code-block:: python

   @tagged_cache(
       timeout=3600,
       tags=[
           "User:{user_id}",
           "Campaign:{campaign_id}",
       ],
       vary_on=["user_id", "campaign_id"],
   )
   def get_campaign_for_user(user_id: int, campaign_id: int):
       return Campaign.objects.filter(id=campaign_id, user=user_id).first()

**What happens internally:**

1. Two tags are created: ``StandardTag("User", "42")`` and ``StandardTag("Campaign", "99")``.
2. ``StandardKey`` embeds *both* versions in the key string. If ``User:42`` is at
   version ``5`` and ``Campaign:99`` is at version ``3``, both are included.
3. If *either* ``User(pk=42).save()`` or ``Campaign(pk=99).save()`` fires, one version
   changes, the composed key changes, and you get a cache miss.
4. The ``vary_on`` ensures ``get_campaign_for_user(42, 99)`` and
   ``get_campaign_for_user(42, 100)`` get separate cache entries.

Custom Key Name and Version
---------------------------

Override the auto-generated key name when you want human-readable cache keys, or use
``version`` to force a cache bust during deployments without touching Redis.

.. code-block:: python

   @tagged_cache(
       timeout=7200,
       tags=["Organization"],
       key_name="OrgListPage",
       version="v2",
   )
   def get_organizations_list():
       return Organization.objects.filter(is_active=True).all()

**What happens internally:**

1. Instead of ``"myapp.views.get_organizations_list"``, the key name is ``"OrgListPage"``.
2. The ``version="v2"`` appends ``_vv2`` to the key name → ``"OrgListPage_vv2"``.
3. If you later change ``version="v3"``, every cached entry under ``v2`` becomes
   unreachable — a deployment-time cache bust without clearing Redis.

Async Functions
---------------

For async views or async service functions, use ``cached_async``. The internal logic
is identical to ``tagged_cache`` — the only difference is the wrapper is an ``async def``
that ``await``\s the decorated function.

.. code-block:: python

   from fragmented_keys_django.cache_utils.decorators import cached_async

   @cached_async(
       timeout=3600,
       tags=["User:{user_id}"],
   )
   async def get_user_data_async(user_id: int):
       return await async_user_query(user_id)

**What happens internally:**

1. ``cached_async`` in ``decorators.py`` is a near-copy of ``tagged_cache``, but the
   inner wrapper is ``async def`` and uses ``result = await func(*args, **kwargs)``
   instead of ``result = func(...)``.
2. Tag resolution and key composition are synchronous (string operations + Redis reads).
   Only the decorated function itself is awaited.
3. Django's cache API (``cache.get``/``cache.set``) is called synchronously — Django's
   cache backends are sync-only. The async boundary is just around your function.

Class Methods
-------------

Works on regular methods. Note that ``self`` is ``args[0]``, so parameter indices shift
by one — but the decorator handles this transparently via ``inspect.signature``.

.. code-block:: python

   class ReportGenerator:
       @tagged_cache(
           timeout=3600,
           tags=["Report:{org_id}"],
           vary_on=["org_id", "report_type"],
       )
       def generate_report(self, org_id: int, report_type: str):
           return compile_report_data(org_id, report_type)

**What happens internally:**

1. ``inspect.signature(func)`` sees parameters ``["self", "org_id", "report_type"]``.
2. When resolving ``{org_id}``, it finds ``org_id`` at index ``1``. Since ``self`` is
   ``args[0]`` and ``org_id`` is ``args[1]``, the resolution works correctly.
3. ``self`` is not in ``vary_on``, so different instances of ``ReportGenerator`` share
   the same cache — the key only varies by ``org_id`` and ``report_type``. If you want
   per-instance caching, add an instance identifier to ``vary_on``.

View Functions
--------------

The decorator works directly on Django view functions. The function's arguments (from
URL kwargs, ``request.GET``, etc.) are available for tag resolution and ``vary_on``.

.. code-block:: python

   from django.http import JsonResponse

   @tagged_cache(
       timeout=300,
       tags=["API", "Organization:{org_id}"],
       vary_on=["org_id", "page"],
   )
   def organization_api_view(request, org_id, page=1):
       org = Organization.objects.get(pk=org_id)
       return JsonResponse({"name": org.name})

**What happens internally:**

1. ``request`` is ``args[0]``, ``org_id`` is ``args[1]``, ``page`` is ``args[2]``
   or a kwarg with default ``1``.
2. Tag resolution uses ``inspect.signature(func)`` to map parameter names to positional
   indices. ``"Organization:{org_id}"`` resolves ``org_id`` from ``args[1]``.
3. ``vary_on=["org_id", "page"]`` means ``/api/orgs/5/?page=1`` and
   ``/api/orgs/5/?page=2`` get separate cache entries.
4. The ``"API"`` tag has no placeholder — it's a global tag. Incrementing
   ``StandardTag("API").increment()`` invalidates *all* cached results of this view
   across all orgs and pages.

.. admonition:: Caveat

   The decorator caches the ``JsonResponse`` *object*. If your response includes
   request-specific data (CSRF tokens, session info), those get cached too. Use
   this pattern for stateless API endpoints.
