# Fragmented Keys Django Integration

A Django cache backend adapter and utilities for the fragmented_keys library, providing automatic cache invalidation through versioned tag-instance pairs.

## Features

- **Automatic cache invalidation**: Tags auto-increment on model changes via Django signals
- **Gradual migration**: Operates side-by-side with existing Django cache patterns
- **No orphan keys**: Cache entries naturally expire via TTL, no explicit deletion needed
- **Decorator-based API**: Clean `@tagged_cache` decorator for easy adoption
- **Model-based invalidation**: Register models for auto-invalidation on save/delete
- **Flexible tagging**: Support for model, list, aggregate, and custom tag patterns

## Installation

The package is included in the project as a local package. Add it to requirements.txt:

```txt
fragmented-keys==1.1
-e ./fragmented_keys_django
```

Then install:

```bash
pip install -e ./fragmented_keys_django
```

## Quick Start

### 1. Configure Django Settings

Add the fragmented cache backend to your settings.py:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
    "fragmented": {
        "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
        "CACHE_NAME": "default",
        "PREFIX": "NOZ_FRAG",
    }
}
```

### 2. Register Models for Auto-Invalidation

```python
# In your app's AppConfig.ready() or a signals.py file
from django.contrib.auth.models import User
from myapp.models import MyModel

from fragmented_keys_django import ModelTagManager

ModelTagManager.register_model(User)
ModelTagManager.register_model(MyModel, tag_name='CustomName')
```

### 3. Use the @tagged_cache Decorator

```python
from fragmented_keys_django import tagged_cache

@tagged_cache(
    timeout=3600,
    tags=['Dashboard', 'User:{user_id}'],
    vary_on=['user_id', 'filter_type']
)
def get_dashboard_statistics(user_id: int, filter_type: str):
    # Expensive computation
    data = fetch_from_database(user_id, filter_type)
    return data
```

## Usage Examples

### Decorator Pattern (Recommended)

```python
from fragmented_keys_django import tagged_cache

@tagged_cache(
    timeout=3600,
    tags=['User:{user_id}', 'Profile:{user_id}'],
    vary_on=['user_id']
)
def get_user_profile(user_id: int):
    return User.objects.get(pk=user_id).profile
```

When the user with `user_id=42` is saved, the auto-increment makes all
cache entries tagged with `User:42` or `Profile:42` resolve to new keys,
effectively invalidating the cache.

### Manual Tag Management

```python
from fragmented_keys_django import model_tag, list_tag
from fragmented_keys import StandardKey

# Build cache key with multiple tags
user_tag = model_tag('User', str(user_id))
campaign_tag = model_tag('Campaign', str(campaign_id))

key = StandardKey('CampaignStats', [user_tag, campaign_tag])
cache_key = key.get_key_str()

# Use with Django cache
from django.core.cache import cache
result = cache.get(cache_key)
if result is None:
    result = compute_statistics()
    cache.set(cache_key, result, timeout=3600)
```

### Model Auto-Invalidation

```python
from fragmented_keys_django import ModelTagManager

# Register models
ModelTagManager.register_model(User)
ModelTagManager.register_model(Donation, tag_name='Donations')

# Now any cache tagged with 'User:{pk}' auto-invalidates on user.save()
user = User.objects.get(pk=42)
user.save()  # Increments User:42 tag -> cache invalidated
```

### Manual Invalidation

```python
from fragmented_keys_django import ModelTagManager

# Invalidate all caches for a specific user
ModelTagManager.invalidate_model_tag(User, 42)
```

## Tag Factory Functions

### model_tag
```python
from fragmented_keys_django import model_tag

user_tag = model_tag('User', str(user_id))
```

### list_tag
```python
from fragmented_keys_django import list_tag

donations_tag = list_tag('Donations', str(user_id))
```

### aggregate_tag
```python
from fragmented_keys_django import aggregate_tag

stats_tag = aggregate_tag('DashboardStats', f'daily_{user_id}')
```

## API Reference

### tagged_cache Decorator

```python
@tagged_cache(
    timeout=3600,              # Cache timeout in seconds
    tags=['Tag:{param}'],      # Tag templates with placeholders
    vary_on=['param1', 'param2'],  # Parameters to vary the cache key
    version='v1',              # Optional version string
    key_name='custom_key',     # Optional custom key name
    cache_name='default'       # Django cache alias
)
def my_function(param1, param2):
    ...
```

### ModelTagManager

```python
# Register a model
ModelTagManager.register_model(model, tag_name=None, auto_connect=True)

# Manually invalidate a model's tag
ModelTagManager.invalidate_model_tag(model_class_or_name, pk)

# Check if a model is registered
ModelTagManager.is_registered(model)

# Get all registered models
ModelTagManager.get_registered_models()

# Unregister a model
ModelTagManager.unregister_model(model)
```

### Configuration

```python
from fragmented_keys_django import configure_fragmented_keys

# Configure globally (typically in AppConfig.ready() or settings.py)
configure_fragmented_keys(
    cache_name='default',
    prefix='NOZ'
)
```

### Tag-Aware Backend API

The backend exposes `*_with_tags` methods for direct tag-aware caching without the decorator. Useful in services, management commands, or anywhere a decorator doesn't fit.

```python
from django.core.cache import caches

cache = caches["fragmented"]

# Set with tags (tuples or StandardTag objects)
cache.set_with_tags("user_profile", profile_data, [("User", "42")], timeout=3600)

# Get with tags
data = cache.get_with_tags("user_profile", [("User", "42")], default=None)

# Get-or-set (default can be a callable)
data = cache.get_or_set_with_tags(
    "user_profile",
    lambda: expensive_query(42),
    [("User", "42")],
    timeout=3600,
)

# Delete a specific tagged entry
cache.delete_with_tags("user_profile", [("User", "42")])

# Invalidate all entries depending on these tags
cache.invalidate_tags([("User", "42")])

# Introspection
version = cache.get_tag_version("User", "42")
```

Tags can be `(name, instance)` tuples, `StandardTag` objects, or a mix of both.

Use `group_id` to namespace keys that share the same base name and tags:

```python
cache.set_with_tags("stats", data_a, tags, group_id="weekly")
cache.set_with_tags("stats", data_b, tags, group_id="monthly")
```

---

## Migration Guide: Vanilla Django to Fragmented Keys

This guide is for projects currently using Django's built-in `cache.get()`/`cache.set()` with manual key construction and manual invalidation. It walks through adopting fragmented keys using either the `@tagged_cache` decorator, the tag-aware backend API, or both.

### Before: Typical Vanilla Django Caching

```python
# Building keys by hand
cache_key = f"user_profile_{user_id}"
data = cache.get(cache_key)
if data is None:
    data = User.objects.get(pk=user_id).profile
    cache.set(cache_key, data, timeout=3600)

# Manual invalidation scattered across signal handlers
@receiver(post_save, sender=User)
def invalidate_user_cache(sender, instance, **kwargs):
    cache.delete(f"user_profile_{instance.pk}")
    cache.delete(f"user_dashboard_{instance.pk}")
    cache.delete(f"user_donations_{instance.pk}")
    # ... easy to forget one
```

**Problems this creates:**
- Key construction is duplicated and fragile
- Invalidation is manual — miss one `cache.delete()` and you serve stale data
- No way to invalidate "all keys that depend on User 42" without tracking every key

### Phase 1: Install & Configure

```bash
pip install fragmented-keys
pip install -e ./fragmented_keys_django
```

```python
# settings.py
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
    "fragmented": {
        "BACKEND": "fragmented_keys_django.cache_backends.django_backend.FragmentedKeysCacheBackend",
        "CACHE_NAME": "default",   # sits on top of "default"
        "PREFIX": "NOZ",
    },
}
```

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from fragmented_keys_django import ModelTagManager
        from django.contrib.auth.models import User
        from myapp.models import Donation

        ModelTagManager.register_model(User)
        ModelTagManager.register_model(Donation)
```

Now `User.save()` and `Donation.save()` automatically increment tag versions. No signal handlers to write.

### Phase 2: Convert Cache Calls

Pick one approach per call site — decorator or backend API.

#### Option A: `@tagged_cache` Decorator

Best for: view helpers, service functions, anywhere you wrap a computation.

```python
# BEFORE
def get_user_profile(user_id):
    key = f"user_profile_{user_id}"
    data = cache.get(key)
    if data is None:
        data = User.objects.get(pk=user_id).profile
        cache.set(key, data, 3600)
    return data

# AFTER
from fragmented_keys_django import tagged_cache

@tagged_cache(
    timeout=3600,
    tags=["User:{user_id}"],
    vary_on=["user_id"],
)
def get_user_profile(user_id: int):
    return User.objects.get(pk=user_id).profile
```

#### Option B: Tag-Aware Backend API

Best for: management commands, services, places where a decorator is awkward.

```python
# BEFORE
cache_key = f"campaign_stats_{campaign_id}_{user_id}"
data = cache.get(cache_key)
if data is None:
    data = compute_campaign_stats(campaign_id, user_id)
    cache.set(cache_key, data, 3600)

# Manual invalidation in signal
cache.delete(f"campaign_stats_{campaign_id}_{user_id}")

# AFTER
from django.core.cache import caches
frag = caches["fragmented"]

tags = [("Campaign", str(campaign_id)), ("User", str(user_id))]
data = frag.get_or_set_with_tags(
    "campaign_stats",
    lambda: compute_campaign_stats(campaign_id, user_id),
    tags,
    timeout=3600,
)
# No manual invalidation needed — ModelTagManager handles it
```

### Phase 3: Remove Old Invalidation Code

Once a cache call is converted, delete the corresponding manual `cache.delete()` calls and signal handlers. The tag version increment handles invalidation automatically.

```python
# DELETE THIS — ModelTagManager replaces it
@receiver(post_save, sender=User)
def invalidate_user_cache(sender, instance, **kwargs):
    cache.delete(f"user_profile_{instance.pk}")
    cache.delete(f"user_dashboard_{instance.pk}")
```

### Phase 4: Verify

```bash
uv run pytest tests/ -v
```

Monitor cache hit rates in production. Old keys expire naturally via TTL — no cache flush needed.

### Conversion Cheat Sheet

| Vanilla Django | Fragmented Keys Equivalent |
|---|---|
| `cache.get(f"key_{id}")` | `frag.get_with_tags("key", [("Model", str(id))])` |
| `cache.set(f"key_{id}", val, 3600)` | `frag.set_with_tags("key", val, [("Model", str(id))], timeout=3600)` |
| `cache.delete(f"key_{id}")` | `frag.invalidate_tags([("Model", str(id))])` (invalidates *all* dependent keys) |
| `@cache_page(3600)` | `@tagged_cache(timeout=3600, tags=[...], vary_on=[...])` |
| Manual signal → `cache.delete()` | `ModelTagManager.register_model(Model)` (automatic) |

## Design Philosophy

The fragmented_keys approach differs from traditional cache invalidation:

| Traditional | Fragmented Keys |
|------------|-----------------|
| Delete keys explicitly on invalidation | Never delete - create new keys |
| Track all keys in a global set | No key tracking needed |
| Pattern match for invalidation | Tag-based versioning |
| Orphan keys accumulate | Natural TTL expiration |

When a tag is incremented (e.g., on model save), all dependent cache keys
resolve to new hash-based strings, causing cache misses and recomputation.
Old entries simply expire via their original TTL.

## Architecture

```
fragmented_keys_django/
├── cache_backends/
│   ├── handlers.py          # DjangoCacheHandler adapter
│   └── django_backend.py     # FragmentedKeysCacheBackend
├── cache_utils/
│   ├── decorators.py        # @tagged_cache decorator
│   ├── model_helpers.py     # ModelTagManager
│   └── tags.py              # Tag factory utilities
└── config.py                # Configuration utilities
```

## Testing

```bash
# Run tests for the package
python -m pytest tests/
```

## License

MIT