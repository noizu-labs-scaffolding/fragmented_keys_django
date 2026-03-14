Decorator Mode
==============

The ``@tagged_cache`` decorator wraps individual functions with tag-based caching.

Basic Example
-------------

.. code-block:: python

   from fragmented_keys_django import tagged_cache

   @tagged_cache(
       timeout=3600,
       tags=["Dashboard"],
   )
   def get_dashboard_stats():
       return Stats.objects.aggregate(total=Sum("amount"))

User-Specific Tags
------------------

Tag templates use ``{placeholder}`` syntax to extract values from function arguments:

.. code-block:: python

   @tagged_cache(
       timeout=1800,
       tags=["User:{user_id}"],
       vary_on=["user_id"],
   )
   def get_user_dashboard(user_id: int):
       return Dashboard.objects.filter(user_id=user_id).first()

Multiple Tags
-------------

A function can depend on multiple tags. The cache invalidates when **any** tag is incremented:

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

Custom Key Name and Version
---------------------------

.. code-block:: python

   @tagged_cache(
       timeout=7200,
       tags=["Organization"],
       key_name="OrgListPage",
       version="v2",
   )
   def get_organizations_list():
       return Organization.objects.filter(is_active=True).all()

Async Functions
---------------

Use ``cached_async`` for async functions:

.. code-block:: python

   from fragmented_keys_django.cache_utils.decorators import cached_async

   @cached_async(
       timeout=3600,
       tags=["User:{user_id}"],
   )
   async def get_user_data_async(user_id: int):
       return await async_user_query(user_id)

Class Methods
-------------

.. code-block:: python

   class ReportGenerator:
       @tagged_cache(
           timeout=3600,
           tags=["Report:{org_id}"],
           vary_on=["org_id", "report_type"],
       )
       def generate_report(self, org_id: int, report_type: str):
           return compile_report_data(org_id, report_type)

View Functions
--------------

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
