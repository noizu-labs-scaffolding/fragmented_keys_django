# Fragmented Keys Django - Usage Examples

This document provides practical examples for using the fragmented_keys_django package in your Django application.

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [Model Registration](#model-registration)
3. [Using the Decorator](#using-the-decorator)
4. [Manual Tag Management](#manual-tag-management)
5. [Advanced Patterns](#advanced-patterns)

---

## Basic Setup

### 1. Configure in Django Settings

Add to your `settings.py`:

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

### 2. Configure in AppConfig

Create `yourapp/apps.py`:

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

---

## Model Registration

### Register Models for Auto-Invalidation

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

### Manual Invalidation

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

---

## Using the Decorator

### Basic Example

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

### With User-Specific Tags

```python
@tagged_cache(
    timeout=1800,                    # 30 minutes
    tags=['User:{user_id}'],         # Auto-invalidates when user changes
    vary_on=['user_id'],             # Key varies by user_id
)
def get_user_dashboard(user_id: int):
    return Dashboard.objects.filter(user_id=user_id).first()
```

### Multiple Tags

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

### Custom Key Name and Version

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

### Using Different Cache Backend

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

### Async Function Support

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

---

## Manual Tag Management

### Using Tag Factories

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

### Build Composite Key Helper

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

---

## Advanced Patterns

### View Function Caching

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

### Class Method Caching

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

### Property Caching (via Helper)

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

### Multi-Level Caching

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

### Custom Tag Templates

```python
# Advanced tag template with multiple variables
@tagged_cache(
    tags=[f'User:{user_id}:Role:{role_id}'],
    vary_on=['user_id', 'role_id'],
)
def get_user_role_permissions(user_id: int, role_id: int):
    return Permissions.objects.filter(user_id=user_id, role_id=role_id)
```

---

## Real-World Examples

### Example 1: Dashboard View

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

### Example 2: API Response Caching

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

### Example 3: Manual Invalidation on External Events

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

---

## Testing with Fragmented Keys

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