# Fragmented Keys Django - Usage Examples

This document provides practical examples for using the fragmented_keys_django package in your Django application. Each example includes a description of the pattern, the code, and a deep dive into what happens internally so you can build a mental model of the system without reading the source.

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [Model Registration](#model-registration)
3. [Using the Decorator](#using-the-decorator)
4. [Manual Tag Management](#manual-tag-management)
5. [Advanced Patterns](#advanced-patterns)

---

## Basic Setup

### 1. Configure in Django Settings

The fragmented cache backend sits *on top of* your existing cache. It doesn't replace Redis/Memcached — it uses your existing backend for storage while adding tag-versioned key composition on top.

```python
CACHES = {
    # Your existing cache
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
    # Fragmented keys cache (side-by-side)
    "fragmented": {
        "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
        "CACHE_NAME": "default",
        "PREFIX": "YOUR_APP",
    }
}
```

**What happens internally:**

1. `FragmentedKeysCacheBackend.__init__()` reads `CACHE_NAME` and creates a `DjangoCacheHandler` wrapping your `"default"` cache.
2. The handler adapts Django's cache API (which stores/returns arbitrary Python objects) to the `fragmented_keys.CacheHandler` protocol (which works with strings). This adapter lives in `cache_backends/handlers.py`.
3. `PREFIX` is passed to `Configuration.set_global_prefix()` — it namespaces all tag version keys in Redis so multiple apps sharing the same Redis instance don't collide.
4. Your existing `"default"` cache continues to work normally. The `"fragmented"` backend is additive — you can adopt it incrementally.

### 2. Configure in AppConfig

This is where you wire up the library at Django startup. `AppConfig.ready()` runs once after all apps are loaded, making it the right place for signal registration and global configuration.

```python
from django.apps import AppConfig

class YourAppConfig(AppConfig):
    name = 'yourapp'

    def ready(self):
        # Configure fragmented_keys
        from fragmented_keys_django import configure_fragmented_keys
        configure_fragmented_keys(
            cache_name='default',
            prefix='YOUR_APP'
        )

        # Register models for auto-invalidation
        from fragmented_keys_django import ModelTagManager
        from django.contrib.auth.models import User
        from .models import YourModel

        ModelTagManager.register_model(User)
        ModelTagManager.register_model(YourModel)
```

**What happens internally:**

1. `configure_fragmented_keys()` creates a `DjangoCacheHandler` and calls `Configuration.set_default_cache_handler()` — this means any `StandardTag` or `StandardKey` created later will automatically use your Django cache for version storage without needing to pass a handler explicitly.
2. `ModelTagManager.register_model(User)` does two things:
   - Stores the mapping `User -> "User"` in `_registered_models` (a class-level dict).
   - Calls `connect_signals(User)`, which hooks `post_save` and `post_delete` signals with `weak=False` (so the handler isn't garbage collected).
3. From this point on, any `User.save()` or `User.objects.get(pk=42).delete()` triggers `_on_model_change`, which calls `StandardTag("User", "42").increment()`.

---

## Model Registration

### Register Models for Auto-Invalidation

Registration connects Django's ORM signals to the tag versioning system. When a registered model instance is saved or deleted, its corresponding tag version is automatically incremented — no manual cache management needed.

```python
from fragmented_keys_django import ModelTagManager
from django.contrib.auth.models import User
from .models import Donation, Campaign, Organization

# Register with default model name
ModelTagManager.register_model(User)              # Tag: User:{pk}
ModelTagManager.register_model(Donation)          # Tag: Donation:{pk}

# Register with custom tag name
ModelTagManager.register_model(Campaign, tag_name='Campaign')
ModelTagManager.register_model(Organization, tag_name='Org')
```

**What happens internally:**

1. For each `register_model()` call, the model class is stored as a key in `ModelTagManager._registered_models` with the tag name as the value. The default tag name is `model.__name__` (e.g., `"User"`).
2. `connect_signals()` disconnects any existing handlers first (to prevent duplicate registrations if `ready()` runs twice), then connects fresh `post_save` and `post_delete` handlers.
3. When `Organization(pk=7).save()` fires:
   - Django emits `post_save` with `sender=Organization, instance=<Organization pk=7>`.
   - `_on_model_change` looks up `Organization` in `_registered_models` → finds `"Org"`.
   - Creates `StandardTag("Org", "7")` and calls `.increment()`.
   - This writes a new version number to Redis under a key like `YOUR_APP:tag:Org:7`.
4. **Scope is per-instance.** Only `Org:7` is incremented. Caches tagged with `Org:3` or `Org:99` are untouched.

**Why `tag_name` matters:** If you register `Organization` with `tag_name='Org'`, your `@tagged_cache` decorators must use `tags=['Org:{org_id}']` — not `'Organization:{org_id}'`. The tag name is the link between signal-driven invalidation and cache key composition.

### Manual Invalidation

Use manual invalidation for changes that bypass Django's ORM — bulk SQL updates, raw queries, external webhooks, or Celery tasks that modify data without calling `model.save()`.

```python
from fragmented_keys_django import ModelTagManager

# Invalidate cache for a specific user
ModelTagManager.invalidate_model_tag(User, 42)

# Invalidate by model name string
ModelTagManager.invalidate_model_tag('User', 42)

# Check if model is registered
if ModelTagManager.is_registered(User):
    print("User model is registered for auto-invalidation")
```

**What happens internally:**

1. `invalidate_model_tag(User, 42)` looks up the tag name for `User` in `_registered_models` (→ `"User"`), creates `StandardTag("User", "42")`, and calls `.increment()`.
2. The string overload (`'User'`) iterates `_registered_models` to find a model whose `__name__` matches, then does the same thing.
3. `.increment()` bumps the version counter stored in Redis. The next time any `StandardKey` containing `User:42` calls `get_key_str()`, it reads the new version, composes a different key string, and the old cached value is effectively invisible (still in Redis, but unreachable — it expires via TTL).
4. Returns `True` on success, `False` if the model isn't registered or an error occurs.

---

## Using the Decorator

### Basic Example

The simplest use case: cache an expensive computation and tie its invalidation to a tag. When the tag version changes, the cache automatically misses without any explicit delete.

```python
from fragmented_keys_django import tagged_cache

@tagged_cache(
    timeout=3600,          # Cache for 1 hour
    tags=['Dashboard'],    # Tag for invalidation
)
def get_dashboard_stats():
    # Expensive computation
    return Stats.objects.aggregate(total=Sum('amount'))
```

**What happens internally — first call:**

1. The decorator wrapper in `decorators.py` runs.
2. **Tag resolution:** For `'Dashboard'` (no `{placeholder}`), `parse_tag_template` returns `("Dashboard", "")`. `resolve_tag_instance` returns `""`. A `StandardTag("Dashboard", "")` is created.
3. **Key name:** Since no `key_name` was passed, the decorator uses `f"{func.__module__}.{func.__qualname__}"` — something like `"myapp.views.get_dashboard_stats"`. No `vary_on` params, so nothing is appended.
4. **Key composition:** `StandardKey("myapp.views.get_dashboard_stats", [dashboard_tag]).get_key_str()` queries Redis for `Dashboard`'s current version (say, `1`), then produces a deterministic key string embedding that version.
5. **Cache lookup:** `cache.get(cache_key)` → `None` (miss). The function runs, result is stored with `cache.set(cache_key, result, timeout=3600)`.

**What happens on invalidation:**

To invalidate, you'd call `StandardTag('Dashboard').increment()` somewhere (there's no model auto-invalidation here since `'Dashboard'` isn't tied to a model). This bumps the version to `2`. Next call to `get_dashboard_stats()` composes a key with version `2` — different string, cache miss, function re-executes.

**Why no explicit delete is needed:** The old cached value (keyed with version `1`) is still in Redis but nobody will ever look it up again. It expires naturally via the 1-hour TTL.

### With User-Specific Tags

This pattern caches per-user results. The `{user_id}` placeholder in the tag template is resolved from the function's arguments, so each user gets their own cache entry *and* their own invalidation scope.

```python
@tagged_cache(
    timeout=1800,                    # 30 minutes
    tags=['User:{user_id}'],         # Auto-invalidates when user changes
    vary_on=['user_id'],             # Key varies by user_id
)
def get_user_dashboard(user_id: int):
    return Dashboard.objects.filter(user_id=user_id).first()
```

**What happens internally when called with `user_id=42`:**

1. **Tag resolution:** `parse_tag_template('User:{user_id}')` returns `("User", "{user_id}")`. `resolve_tag_instance` extracts `"user_id"` from the placeholder, then uses `inspect.signature(func)` to find which positional argument index `user_id` occupies. It finds `args[0] = 42`, so the tag becomes `StandardTag("User", "42")`.
2. **Key name with vary_on:** The base key is `"myapp.views.get_user_dashboard"`. Since `vary_on=['user_id']`, the decorator appends `_user_id_42` → `"myapp.views.get_user_dashboard_user_id_42"`.
3. **Key composition:** `StandardKey("...dashboard_user_id_42", [user_tag]).get_key_str()` looks up `User:42`'s version in Redis and embeds it.
4. **Cache hit/miss:** Standard get-or-compute flow.

**When `User(pk=42).save()` fires:** `ModelTagManager._on_model_change` increments `User:42`'s version. Next call to `get_user_dashboard(42)` composes a different key → miss → recompute. Meanwhile, `get_user_dashboard(7)` still hits its cache because `User:7` hasn't changed.

### Multiple Tags

When a cache entry depends on multiple entities, list all relevant tags. The cache is invalidated when *any* of the tags change — it's a logical AND of freshness.

```python
@tagged_cache(
    timeout=3600,
    tags=[
        'User:{user_id}',        # Invalidates on user change
        'Campaign:{campaign_id}', # Invalidates on campaign change
    ],
    vary_on=['user_id', 'campaign_id'],
)
def get_campaign_for_user(user_id: int, campaign_id: int):
    return Campaign.objects.filter(id=campaign_id, user=user_id).first()
```

**What happens internally:**

1. Two tags are created: `StandardTag("User", "42")` and `StandardTag("Campaign", "99")`.
2. `StandardKey` embeds *both* versions in the key string. If `User:42` is at version `5` and `Campaign:99` is at version `3`, the key includes both.
3. If *either* `User(pk=42).save()` or `Campaign(pk=99).save()` fires, one version changes, the composed key changes, and you get a cache miss.
4. The `vary_on` ensures `get_campaign_for_user(42, 99)` and `get_campaign_for_user(42, 100)` get separate cache entries.

### Custom Key Name and Version

Override the auto-generated key name when you want human-readable cache keys, or use `version` to force a cache bust during deployments.

```python
@tagged_cache(
    timeout=7200,
    tags=['Organization'],
    key_name='OrgListPage',  # Custom base key name
    version='v2',           # Version for cache-busting
)
def get_organizations_list():
    return Organization.objects.filter(is_active=True).all()
```

**What happens internally:**

1. Instead of `"myapp.views.get_organizations_list"`, the key name is `"OrgListPage"`.
2. The `version='v2'` appends `_vv2` to the key name → `"OrgListPage_vv2"`.
3. If you later change `version='v3'`, every cached entry under `v2` becomes unreachable — a deployment-time cache bust without touching Redis.

### Using Different Cache Backend

You can point the decorator at a specific Django cache alias. This is useful if you've set up the `FragmentedKeysCacheBackend` under a separate alias.

```python
@tagged_cache(
    timeout=3600,
    tags=['API'],
    cache_name='fragmented',  # Use the fragmented cache backend
)
def external_api_call():
    # Expensive external API call
    return requests.get('https://api.example.com/data').json()
```

**What happens internally:**

1. The decorator calls `caches['fragmented']` instead of `caches['default']`.
2. The rest of the flow is identical — tag resolution, key composition, get-or-compute. The difference is which Django cache backend performs the actual `get`/`set`.
3. If `'fragmented'` points to `FragmentedKeysCacheBackend`, the backend's own `DjangoCacheHandler` is used. But the decorator builds its own `StandardKey` regardless — the cache backend here is just storage.

### Async Function Support

For async views or async service functions, use `cached_async`. The internal logic is identical to `tagged_cache` — the only difference is the wrapper is an `async def` that `await`s the decorated function.

```python
from fragmented_keys_django import cached_async

@cached_async(
    timeout=3600,
    tags=['User:{user_id}'],
)
async def get_user_data_async(user_id: int):
    # Async database query
    return await async_user_query(user_id)
```

**What happens internally:**

1. `cached_async` in `decorators.py` is a near-copy of `tagged_cache`, but the inner `wrapper` is `async def` and uses `result = await func(*args, **kwargs)` instead of `result = func(...)`.
2. Tag resolution and key composition are synchronous (they're just string operations and Redis reads) — only the decorated function itself is awaited.
3. Django's cache API (`cache.get`/`cache.set`) is called synchronously. This is fine because Django's cache backends are sync-only; the async boundary is just around your function.

---

## Manual Tag Management

### Using Tag Factories

Tag factories are semantic aliases — they all create a `StandardTag` under the hood. The different names (`model_tag`, `list_tag`, `aggregate_tag`) exist to make your code's *intent* clear to future readers.

```python
from fragmented_keys import StandardKey
from fragmented_keys_django import model_tag, list_tag, aggregate_tag
from django.core.cache import cache

# Model instance tag
user_tag = model_tag('User', str(user_id))

# List/aggregation tag
user_donations_tag = list_tag('Donations', str(user_id))

# Aggregate/statistics tag
daily_stats_tag = aggregate_tag('DailyStats', f'{user_id}_{date}')

# Create composite key
key = StandardKey('UserDashboard', [user_tag, user_donations_tag])
cache_key = key.get_key_str()

# Use with cache
result = cache.get(cache_key)
if result is None:
    result = compute_dashboard()
    cache.set(cache_key, result, timeout=3600)
```

**What happens internally:**

1. `model_tag('User', '42')` calls `StandardTag('User', '42')`. `list_tag` and `aggregate_tag` do the same thing — there's no behavioral difference, only semantic naming (see `tags.py`).
2. `StandardKey('UserDashboard', [user_tag, user_donations_tag])` creates a composite key object that holds a base name and a list of tags.
3. `key.get_key_str()` queries Redis for the current version of each tag, then combines `base_name + tag_name + instance + version` for each tag into a single deterministic string. This is the actual Redis key you'll use with `cache.get()`.
4. If either `User:42` or `Donations:42` is incremented, `get_key_str()` produces a different string → cache miss.

**When to use this vs. `@tagged_cache`:** Use tag factories when you need cache logic in places where a decorator doesn't fit — management commands, service classes, Celery tasks, or when you need conditional caching logic.

### Build Composite Key Helper

A convenience function that combines tag creation and key name construction in one call, reducing boilerplate when you have multiple tags and vary parameters.

```python
from fragmented_keys import StandardKey
from fragmented_keys_django import build_composite_key

# Build tags and key name together
tag_objs, key_name = build_composite_key(
    base_name='UserProfile',
    tags=[('User', '42')],
    vary_params=[('include_history', 'true')]
)

# Create the actual key
key = StandardKey(key_name, tag_objs)
cache_key = key.get_key_str()
```

**What happens internally:**

1. `build_composite_key` iterates the `tags` list, creating `StandardTag(name, instance)` for each tuple.
2. It builds the key name by appending vary params: `"UserProfile"` + `"_include_history_true"` → `"UserProfile_include_history_true"`.
3. Returns the tag objects and composed key name as a tuple — you still need to create the `StandardKey` and call `get_key_str()` yourself.
4. This is essentially what the `@tagged_cache` decorator does internally (see `decorators.py` lines 66-89), exposed as a standalone function.

---

## Advanced Patterns

### View Function Caching

The decorator works directly on Django view functions. The function's arguments (from URL kwargs, `request.GET`, etc.) are available for tag resolution and `vary_on`.

```python
from django.http import JsonResponse

@tagged_cache(
    timeout=300,
    tags=['API', 'Organization:{org_id}'],
    vary_on=['org_id', 'page'],
)
def organization_api_view(request, org_id, page=1):
    org = Organization.objects.get(pk=org_id)
    data = {
        'name': org.name,
        'reviews': org.reviews.all()[page*20:(page+1)*20],
    }
    return JsonResponse(data)
```

**What happens internally:**

1. `request` is `args[0]`, `org_id` is `args[1]`, `page` is `args[2]` or a kwarg with default `1`.
2. Tag resolution uses `inspect.signature(func)` to map parameter names to positional indices. `'Organization:{org_id}'` resolves `org_id` from `args[1]`.
3. `vary_on=['org_id', 'page']` means `/api/orgs/5/?page=1` and `/api/orgs/5/?page=2` get separate cache entries.
4. The `'API'` tag has no placeholder — it's a global tag. Incrementing `StandardTag('API').increment()` invalidates *all* cached results of this view across all orgs and pages.

**Caveat:** The decorator caches the `JsonResponse` *object*. If your response includes request-specific data (CSRF tokens, session info), those get cached too. Use this pattern for stateless API endpoints.

### Class Method Caching

Works on regular methods. Note that `self` is `args[0]`, so parameter indices shift by one — but the decorator handles this transparently via `inspect.signature`.

```python
class ReportGenerator:
    @tagged_cache(
        timeout=3600,
        tags=['Report:{org_id}'],
        vary_on=['org_id', 'report_type'],
    )
    def generate_report(self, org_id: int, report_type: str):
        # Generate expensive report
        return compile_report_data(org_id, report_type)
```

**What happens internally:**

1. `inspect.signature(func)` sees parameters `['self', 'org_id', 'report_type']`.
2. When resolving `{org_id}`, it finds `org_id` at index `1` in the parameter list. Since `self` is `args[0]` and `org_id` is `args[1]`, the resolution works correctly.
3. `self` is not in `vary_on`, so different instances of `ReportGenerator` share the same cache — the key only varies by `org_id` and `report_type`. If you want per-instance caching, add an instance identifier to `vary_on`.

### Property Caching (via Helper)

For model properties that are expensive to compute, you can build a descriptor that uses fragmented keys internally. This pattern gives you cached properties that auto-invalidate when the model instance changes.

```python
class CachedProperty:
    def __init__(self, timeout=3600, tags=None):
        self.timeout = timeout
        self.tags = tags or []

    def __get__(self, instance, owner):
        if instance is None:
            return self

        key_parts = [owner.__name__, 'property', str(instance.pk)]
        key_name = '_'.join(key_parts)

        from fragmented_keys import StandardKey, StandardTag
        tag_objs = [StandardTag(tag, str(instance.pk)) for tag in self.tags]
        key = StandardKey(key_name, tag_objs)
        cache_key = key.get_key_str()

        from django.core.cache import cache
        value = cache.get(cache_key)
        if value is not None:
            return value

        # Compute and cache
        value = self.get_value(instance)
        cache.set(cache_key, value, timeout=self.timeout)
        return value

    def get_value(self, instance):
        raise NotImplementedError


# Usage in model
class Organization(models.Model):
    name = models.CharField(max_length=255)

    @cached_property(tags=['Organization'])
    def expensive_computation(self):
        # Expensive computation using self
        return compute_something(self)
```

**What happens internally:**

1. On property access (`org.expensive_computation`), `__get__` fires.
2. It builds a key name like `"Organization_property_42"` and creates `StandardTag("Organization", "42")`.
3. `get_key_str()` embeds the tag version — if `Organization:42` was incremented (by a `save()`), the key string changes and the property recomputes.
4. This is the same get-or-compute pattern as the decorator, just implemented as a Python descriptor.

**Trade-off:** Every property access hits Redis twice (once for the tag version, once for the cached value). For truly hot paths, consider an in-memory LRU as an L1 cache.

### Multi-Level Caching

Different functions can share the same tags but with different TTLs. Short-lived caches (session data) and long-lived caches (aggregate stats) both invalidate when the user changes, but they recompute at different rates.

```python
@tagged_cache(
    timeout=300,      # 5 minutes
    tags=['Session:{session_id}', 'User:{user_id}'],
)
def get_session_data(session_id, user_id):
    return Session.objects.filter(id=session_id, user_id=user_id).first()

@tagged_cache(
    timeout=3600,     # 1 hour
    tags=['User:{user_id}'],
)
def get_user_stats(user_id):
    return aggregate_user_statistics(user_id)
```

**What happens internally:**

1. Both functions' cache keys embed `User:{user_id}`'s version. When `User(pk=42).save()` fires, *both* functions' caches for `user_id=42` become stale simultaneously.
2. `get_session_data` also depends on `Session:{session_id}` — so it additionally invalidates when the session changes (if you've registered the Session model or manually increment that tag).
3. The 5-minute vs. 1-hour TTL means orphaned keys from `get_session_data` expire faster. This is a nice property — frequently-changing data doesn't linger.

### Custom Tag Templates

For cases where a single tag depends on multiple dimensions, you can encode compound identifiers in the tag instance string.

```python
# Advanced tag template with multiple variables
@tagged_cache(
    tags=[f'User:{user_id}:Role:{role_id}'],
    vary_on=['user_id', 'role_id'],
)
def get_user_role_permissions(user_id: int, role_id: int):
    return Permissions.objects.filter(user_id=user_id, role_id=role_id)
```

**What happens internally:**

1. `parse_tag_template` finds the *first* `{` and *last* `}` in the template string. For `'User:{user_id}:Role:{role_id}'`, it extracts everything before the first `{` as the tag name (`"User"`) and the placeholder region as `"{user_id}:Role:{role_id}"`.
2. `resolve_tag_instance` then extracts the first `{param}` match — so it resolves `user_id` only. The `:Role:{role_id}` part is effectively ignored in tag resolution.
3. **This is a subtle gotcha.** The tag created is `StandardTag("User", "42")`, not a compound tag. To properly depend on both user and role, use two separate tags:

```python
# Correct approach for multi-dimension invalidation
@tagged_cache(
    tags=['User:{user_id}', 'Role:{role_id}'],
    vary_on=['user_id', 'role_id'],
)
def get_user_role_permissions(user_id: int, role_id: int):
    return Permissions.objects.filter(user_id=user_id, role_id=role_id)
```

---

## Real-World Examples

### Example 1: Dashboard View

A complete class-based view showing nested caching — the outer view caches the full response, and an inner method caches a sub-computation with its own tags and TTL.

```python
from django.views import View
from django.http import JsonResponse
from fragmented_keys_django import tagged_cache
from fragmented_keys_django import ModelTagManager

# Register models (do this in AppConfig)
ModelTagManager.register_model(User)
ModelTagManager.register_model(Donation)
ModelTagManager.register_model(Campaign)

class DashboardView(View):
    @tagged_cache(
        timeout=600,
        tags=[
            'User:{user_id}',
            'Dashboard',  # Invalidated when any dashboard data changes
        ],
        vary_on=['user_id', 'date_range'],
    )
    def get(self, request):
        user_id = request.user.id
        date_range = request.GET.get('range', '30d')

        # Dashboard data aggregation
        data = {
            'donations': Donation.objects.filter(user_id=user_id).count(),
            'campaigns': Campaign.objects.filter(user_id=user_id).count(),
            'stats': self._compute_stats(user_id, date_range),
        }

        return JsonResponse(data)

    @tagged_cache(
        timeout=3600,
        tags=['User:{user_id}', 'Stats:{date_range}'],
    )
    def _compute_stats(self, user_id, date_range):
        # Expensive statistics computation
        return complex_aggregation(user_id, date_range)
```

**What happens internally — the nested caching flow:**

1. `DashboardView().get(request)` is called. The outer decorator resolves `user_id` and `date_range` from the function's arguments via `inspect.signature`.
2. If the outer cache misses, the function body runs. It calls `self._compute_stats(user_id, date_range)`.
3. The inner `_compute_stats` has its own decorator. It might hit *its* cache even when the outer missed (e.g., if only the `Dashboard` global tag was incremented but `Stats:{date_range}` hasn't changed).
4. The outer result (a `JsonResponse`) is cached with a 10-minute TTL. The inner stats are cached with a 1-hour TTL. This means stats survive dashboard-level invalidation — they only recompute when user data or stats-specific tags change.

**Invalidation scenarios:**
- `User(pk=42).save()` → both outer and inner caches for `user_id=42` miss (both have `User:{user_id}` tag).
- `StandardTag('Dashboard').increment()` → outer cache misses for *all* users (global tag), but inner `_compute_stats` still hits (no `Dashboard` tag).
- `StandardTag('Stats', '30d').increment()` → inner cache for `date_range='30d'` misses, outer cache also misses because the inner recomputation produces new data.

### Example 2: API Response Caching

REST framework integration. The decorator works with DRF views the same way as vanilla Django views.

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from fragmented_keys_django import tagged_cache

class CampaignListAPI(APIView):
    @tagged_cache(
        timeout=300,
        tags=[
            'CampaignList',
            'Campaign:{campaign_id}',  # List key changes when any campaign changes
        ],
        vary_on=['user_id', 'status'],
    )
    def get(self, request):
        user_id = request.user.id
        status = request.GET.get('status', 'all')

        campaigns = Campaign.objects.filter(user_id=user_id)
        if status != 'all':
            campaigns = campaigns.filter(status=status)

        serializer = CampaignSerializer(campaigns, many=True)
        return Response(serializer.data)
```

**What happens internally:**

1. The tag `'Campaign:{campaign_id}'` tries to resolve `campaign_id` from the function arguments. But `get(self, request)` doesn't have a `campaign_id` parameter — `resolve_tag_instance` will return `""`, creating `StandardTag("Campaign", "")`.
2. This means the tag is effectively a global tag (empty instance). Incrementing `StandardTag("Campaign", "").increment()` or any model save won't automatically hit this unless you manually increment `Campaign:""`.
3. **Better pattern for list invalidation:** Use a `list_tag` or a global tag explicitly, and handle list-level invalidation manually or through a custom signal:

```python
# More explicit approach
@tagged_cache(
    timeout=300,
    tags=['CampaignList'],  # Global tag for all campaign lists
    vary_on=['user_id', 'status'],
)
def get(self, request):
    ...
```

### Example 3: Manual Invalidation on External Events

For webhooks, Celery tasks, management commands, or any code path that modifies data without going through Django's ORM `save()`.

```python
from fragmented_keys_django import ModelTagManager

# Handle external webhook that updates data
def webhook_handler(request):
    data = json.loads(request.body)
    user_id = data.get('user_id')

    # Process updates...

    # Invalidate cache for this user
    ModelTagManager.invalidate_model_tag(User, user_id)

    return JsonResponse({'status': 'ok'})
```

**What happens internally:**

1. The webhook handler modifies data (perhaps via raw SQL or an external service call).
2. `invalidate_model_tag(User, user_id)` increments `StandardTag("User", str(user_id))`.
3. Any `@tagged_cache`-decorated function with `tags=['User:{user_id}']` will miss on next call with that `user_id`.
4. No need to know *which* cache keys exist — the tag version change propagates automatically to all dependent keys.

**Why this is cleaner than vanilla Django:** In traditional caching, you'd need to know every cache key that depends on this user (`"user_profile_42"`, `"user_dashboard_42"`, `"user_stats_42"`, ...) and delete each one. With fragmented keys, you increment one tag and all dependent caches invalidate.

---

## Testing with Fragmented Keys

Testing verifies the full lifecycle: cache miss → cache hit → invalidation → cache miss again.

```python
from django.test import TestCase
from fragmented_keys_django import ModelTagManager, tagged_cache

class CacheTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use a test cache
        from django.core.cache import caches
        cls.test_cache = caches['default']

    def test_cache_invalidation(self):
        user = User.objects.create_user(username='test', id=42)

        # First call - cache miss
        result1 = self.get_user_cache(user.id)
        self.assertIsNotNone(result1)

        # Second call - cache hit
        result2 = self.get_user_cache(user.id)
        self.assertEqual(result1, result2)

        # Invalidate
        ModelTagManager.invalidate_model_tag(User, user.id)

        # Third call - should be cache miss now
        result3 = self.get_user_cache(user.id)

    @tagged_cache(
        timeout=60,
        tags=['User:{user_id}'],
        vary_on=['user_id'],
        cache_name='default',
    )
    def get_user_cache(self, user_id):
        return User.objects.get(pk=user_id)
```

**What happens internally during the test:**

1. **First call:** Tag `User:42` doesn't exist in Redis yet — `StandardTag.get_tag_version()` returns a default (e.g., `0`). Key is composed with version `0`, cache miss, function runs, result stored.
2. **Second call:** Same tag version (`0`), same composed key, cache hit. Function is *not* called.
3. **`invalidate_model_tag`:** Increments `User:42` to version `1`.
4. **Third call:** Tag version is now `1`, composed key is different from the one stored at version `0`. Cache miss, function runs again.

**Testing tip:** Use Django's `override_settings` with a `LocMemCache` backend for fast, isolated tests. The fragmented keys system works with any Django cache backend — it doesn't require Redis for testing.