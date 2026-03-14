# Migration Guide: From Manual Cache Invalidation to Fragmented Keys

This guide provides step-by-step instructions for migrating from the existing manual cache invalidation system (`CACHE_KEY_ARRAY` + `invalidate_cache(prefix)`) to the new fragmented_keys system.

---

## Understanding the Difference

### Current System (Manual)

```python
# GreatNonProfit/caching.py
CACHE_KEY_ARRAY = set()

# Somewhere in code
CACHE_KEY_ARRAY.add('dashboard_stats_42')
cache.set('dashboard_stats_42', data, timeout=3600)

# On model change
def invalidate_on_user_change(sender, instance, **kwargs):
    for key in CACHE_KEY_ARRAY:
        if re.match(f'^{prefix}', key):
            cache.delete(key)
```

**Problems:**
- Must explicitly track every cache key
- Pattern matching to find keys to delete
- Orphan keys can accumulate
- Manual key management is error-prone

### New System (Fragmented Keys)

```python
# Register model once
ModelTagManager.register_model(User)

# Use decorator
@tagged_cache(
    tags=['User:{user_id}'],
    vary_on=['user_id'],
)
def get_user_cache(user_id: int):
    return User.objects.get(pk=user_id)

# Auto-invalidation on model.save()
user = User.objects.get(pk=42)
user.save()  # Cache for user 42 automatically invalidated
```

**Benefits:**
- No key tracking needed
- Tag-based automatic invalidation
- Old keys naturally expire via TTL
- Declarative, easy to understand

---

## Phase 1: Setup (Week 1)

### Step 1.1: Install Dependencies

```bash
pip install fragmented-keys
pip install -e ./fragmented_keys_django
```

Or add to `requirements.txt`:

```txt
fragmented-keys>=0.1.3
-e ./fragmented_keys_django
```

### Step 1.2: Configure Django Settings

Add to `GreatNonProfit/settings.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        }
    },
    "fragmented": {
        "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
        "CACHE_NAME": "default",
        "PREFIX": "NOZ_FRAG",
    }
}
```

### Step 1.3: Create AppConfig

Create `GreatNonProfit/apps.py` (or add to existing):

```python
from django.apps import AppConfig

class GreatNonProfitConfig(AppConfig):
    name = 'GreatNonProfit'

    def ready(self):
        from fragmented_keys_django import configure_fragmented_keys, ModelTagManager

        # Configure fragmented_keys
        configure_fragmented_keys(
            cache_name='default',
            prefix='NOZ'
        )

        # Register models (from existing caching.py signals)
        from customer_management.models import User
        from transations_management.models import Donations
        from campaign.models import campaigns, top_rated_organization
        from reviews.models import reviews_sample, review_comments, review_categories, organization_categories
        from organizations.models import organizations
        from authentication.models import subadmin_management

        ModelTagManager.register_model(User, tag_name='User')
        ModelTagManager.register_model(Donations, tag_name='Donations')
        ModelTagManager.register_model(campaigns, tag_name='Campaign')
        ModelTagManager.register_model(top_rated_organization, tag_name='TopRatedOrg')
        ModelTagManager.register_model(reviews_sample, tag_name='Review')
        ModelTagManager.register_model(review_comments, tag_name='ReviewComment')
        ModelTagManager.register_model(organizations, tag_name='Organization')
        ModelTagManager.register_model(subadmin_management, tag_name='SubAdmin')
```

Update `GreatNonProfit/settings.py`:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'GreatNonProfit.apps.GreatNonProfitConfig',  # Add this
    # ... rest of apps ...
]
```

### Step 1.4: Documentation

Create internal documentation for the team explaining:
- Why we're migrating
- What fragmented_keys does
- How to use the new `@tagged_cache` decorator
- Migration timeline and expectations

---

## Phase 2: Decorator Adoption (Weeks 2-4)

### Step 2.1: Identify Targets

Identify the most frequently cached views/functions. Look for:

1. High-traffic views
2. Functions with existing `cache.get/set` patterns
3. Functions that use `cache_the_data()` or `get_cached_data()` helpers

Example targets:
- Dashboard views (cache key: `dashboard_stats_...`)
- Organization lists (cache key: `orgs_...`)
- Review lists (cache key: `org_review_list_...`)
- Search results (cache key: `search_results_...`)

### Step 2.2: Convert Top Functions

For each target function, convert from pattern:

```python
# OLD (caching.py pattern)
def get_dashboard_data(user_id):
    key = f'dashboard_stats_{user_id}'
    data = get_cached_data(key)
    if data is None:
        data = compute_dashboard(user_id)
        CACHE_KEY_ARRAY.add(key)
        cache_the_data(key, data)
    return data
```

To:

```python
# NEW (fragmented_keys pattern)
@tagged_cache(
    timeout=86400,  # 24 hours
    tags=[
        'Dashboard',      # Global dashboard tag
        'User:{user_id}', # User-specific tag
    ],
    vary_on=['user_id'],
)
def get_dashboard_data(user_id: int):
    return compute_dashboard(user_id)
```

### Step 2.3: Register Models for Invalidation

For models that trigger invalidation, register in AppConfig:

```python
# From existing caching.py
@receiver(post_save, sender=Donations)
@receiver(post_delete, sender=Donations)
def invalidate_on_donations_change(sender, instance, **kwargs):
    invalidate_cache('dashboard')

# Becomes in AppConfig
ModelTagManager.register_model(Donations, tag_name='Donations')
```

Then ensure all cached functions that depend on Donations use tags:

```python
@tagged_cache(
    tags=[
        'Donations:{donation_id}',  # If caching single donation
        'User:{user_id}',           # If caching user's donation list
    ],
    vary_on=['donation_id']  # or ['user_id']
)
def get_donation_details(donation_id, user_id):
    # ...
```

### Step 2.4: Remove Old Keys from CACHE_KEY_ARRAY

As each function is converted, remove its keys from the old tracking system:

```python
# In the converted function, remove these lines:
CACHE_KEY_ARRAY.add(key)  # REMOVE
cache_the_data(key, data)  # Remove, decorator handles it
```

---

## Phase 3: Gradual Migration (Ongoing)

### Step 3.1: Convert View Functions

For each Django view, identify cache usage:

```python
# OLD
def organization_list_view(request):
    cache_key = f'orgs_{filters}'
    orgs = get_cached_data(cache_key)
    if orgs is None:
        orgs = Organization.objects.filter(**filters)
        CACHE_KEY_ARRAY.add(cache_key)
        cache_the_data(cache_key, orgs)
    return render(request, 'orgs.html', {'orgs': orgs})
```

Convert to:

```python
# NEW
@tagged_cache(
    timeout=3600,
    tags=['OrganizationList', 'Filters:{filters_hash}'],
    vary_on=['filters'],
)
def organization_list_view(request, filters):
    orgs = Organization.objects.filter(**filters)
    return render(request, 'orgs.html', {'orgs': orgs})
```

### Step 3.2: Update Signal Handlers

As models are converted, update signal handlers:

```python
# OLD (GreatNonProfit/caching.py)
@receiver(post_save, sender=organizations)
@receiver(post_delete, sender=organizations)
def invalidate_on_organization_change(sender, instance, **kwargs):
    invalidate_cache('dashboard')
    invalidate_cache('search_results_')
    invalidate_cache('org_')
    invalidate_cache('orgs_')
    # ... more prefixes

# Can be simplified to:
@receiver(post_save, sender=organizations)
@receiver(post_delete, sender=organizations)
def invalidate_on_organization_change(sender, instance, **kwargs):
    # No manual prefix matching needed
    # ModelTagManager handles auto-invalidation
    pass  # The decorator tags handle invalidation
```

### Step 3.3: Update Helper Functions

Replace `cache_the_data()` and `get_cached_data()` usage:

```python
# OLD
def get_user_data(user_id):
    key = f'user_data_{user_id}'
    data = get_cached_data(key)
    if data is None:
        data = fetch_user_data(user_id)
        cache_the_data(key, data, 3600)
    return data

# NEW
@tagged_cache(
    timeout=3600,
    tags=['User:{user_id}'],
    vary_on=['user_id'],
)
def get_user_data(user_id: int):
    return fetch_user_data(user_id)
```

---

## Phase 4: Cleanup (Optional - When Migration Complete)

### Step 4.1: Consider Default Backend Change

Optional: Make 'fragmented' the default cache backend:

```python
# CACHES["default"] = FragmentedKeysCacheBackend
# This requires thorough testing first
```

### Step 4.2: Remove Old Inflation Pattern

When migration is complete (>90% of views converted):

1. Remove `CACHE_KEY_ARRAY` from settings.py
2. Remove `invalidate_cache()` function from caching.py
3. Remove manual prefix-matching signal handlers
4. Remove `cache_the_data()` and `get_cached_data()` helpers
5. Update all remaining manual cache.get/set patterns

---

## Testing During Migration

### Unit Testing

For each converted function, add tests:

```python
class CacheMigrationTest(TestCase):
    def test_old_pattern_still_works(self):
        # Ensure cache.get/set still works
        cache.set('test_key', 'value', 60)
        self.assertEqual(cache.get('test_key'), 'value')

    def test_new_pattern_works(self):
        # Test decorator caching
        from your_module import get_user_data

        result1 = get_user_data(42)
        result2 = get_user_data(42)  # Should hit cache

        assert result1 == result2

    def test_tag_invalidation(self):
        from fragmented_keys_django import ModelTagManager
        from your_module import get_user_data

        result1 = get_user_data(42)

        # Invalidate
        ModelTagManager.invalidate_model_tag(User, 42)

        result2 = get_user_data(42)  # Should be cache miss

        # Verify recomputation
        assert result1['computed_at'] != result2['converted_at']
```

### Integration Testing

Test that both systems work together:

```python
def test_side_by_side_operation(self):
    # Old pattern
    cache.set('old_key', 'old_value')
    self.assertEqual(cache.get('old_key'), 'old_value')

    # New pattern
    from your_module import get_new_data
    result = get_new_data(42)

    # Both should work without conflict
    self.assertEqual(cache.get('old_key'), 'old_value')
```

---

## Rollback Plan

If issues arise during migration:

### Option 1: Keep Both Systems Running

- The old `CACHE_KEY_ARRAY` system continues working
- New `@tagged_cache` decorator works independently
- Gradually convert back if needed

### Option 2: Revert Individual Functions

For a recently converted function, revert to old pattern:

```python
# Revert to old pattern
def get_user_data(user_id):
    key = f'user_data_{user_id}'
    data = get_cached_data(key)
    if data is None:
        data = fetch_user_data(user_id)
        cache_the_data(key, data)
    return data

# Remove decorator
@tagged_cache(...)  # DELETE
```

### Option 3: Disable New System

Temporarily disable new cache backend:

```python
# Comment out or remove from settings
# "fragmented": { ... }  # DISABLE

# Remove model registrations in AppConfig
```

---

## Monitoring

### Cache Hit Rates

Monitor cache hit rates in production:

```python
# Add to your metrics collection
from django.core.cache import caches

def log_cache_stats():
    stats = caches['default'].get_client().info('stats')
    hits = stats.get('keyspace_hits', 0)
    misses = stats.get('keyspace_misses', 0)
    hit_rate = hits / (hits + misses) if hits + misses > 0 else 0
    log_metric('cache_hit_rate', hit_rate)
```

### Memory Usage

Monitor Redis memory to ensure orphan keys don't explode:

```bash
# Check memory usage
redis-cli info memory

# Check key count
redis-cli dbsize
```

---

## Common Issues and Solutions

### Issue: Cache Keys Not Invalidating

**Solution:** Ensure models are registered in AppConfig:

```python
# AppConfig.ready()
ModelTagManager.register_model(YourModel)
```

### Issue: Old Pattern Still Working But Slow

**Solution:** Fragmented keys uses MD5 hashing which is fast, but verify:

```python
# Verify tag version is being incremented
from fragmented_keys import StandardTag

tag = StandardTag('User', '42')
tag.increment()

# Tag version should have changed
```

### Issue: Conflicting Keys Between Systems

**Solution:** Ensure different prefixes are used:

```python
# Old system keys: 'dashboard_stats_42'
# New system keys: MD5 hash - won't conflict

# They use different key spaces, so no conflict
```

---

## Summary

| Phase | Actions | Duration |
|-------|---------|----------|
| 1: Setup | Install, configure, document | 1 week |
| 2: Adoption | Convert top 10 functions | 2-4 weeks |
| 3: Migration | Gradual view migration | Ongoing |
| 4: Cleanup | Remove old system | Optional |

**Key Points:**
- Both systems run side-by-side during migration
- No breaking changes required
- Gradual, risk-managed approach
- Easy rollback if needed
- Monitor and test at each step