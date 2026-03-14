# Migration Guide

This guide covers migrating from vanilla Django caching (manual `cache.get()`/`cache.set()` with manual invalidation) to fragmented-keys-django.

## Before: Typical Vanilla Django Caching

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

**Problems:**
- Key construction is duplicated and fragile
- Miss one `cache.delete()` and you serve stale data
- No way to invalidate "all keys that depend on User 42" without tracking every key

## Phase 1: Install & Configure

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
        "CACHE_NAME": "default",
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

## Phase 2: Convert Cache Calls

### Option A: `@tagged_cache` Decorator

Best for view helpers, service functions — anywhere you wrap a computation.

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

### Option B: Tag-Aware Backend API

Best for management commands, services, places where a decorator is awkward.

```python
# BEFORE
cache_key = f"campaign_stats_{campaign_id}_{user_id}"
data = cache.get(cache_key)
if data is None:
    data = compute_campaign_stats(campaign_id, user_id)
    cache.set(cache_key, data, 3600)

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
```

## Phase 3: Remove Old Invalidation Code

Once a cache call is converted, delete the corresponding manual `cache.delete()` calls and signal handlers:

```python
# DELETE THIS — ModelTagManager replaces it
@receiver(post_save, sender=User)
def invalidate_user_cache(sender, instance, **kwargs):
    cache.delete(f"user_profile_{instance.pk}")
    cache.delete(f"user_dashboard_{instance.pk}")
```

## Phase 4: Verify

```bash
uv run pytest tests/ -v
```

Monitor cache hit rates in production. Old keys expire naturally via TTL — no cache flush needed.

## Conversion Cheat Sheet

| Vanilla Django | Fragmented Keys Equivalent |
|---|---|
| `cache.get(f"key_{id}")` | `frag.get_with_tags("key", [("Model", str(id))])` |
| `cache.set(f"key_{id}", val, 3600)` | `frag.set_with_tags("key", val, [("Model", str(id))], timeout=3600)` |
| `cache.delete(f"key_{id}")` | `frag.invalidate_tags([("Model", str(id))])` |
| `@cache_page(3600)` | `@tagged_cache(timeout=3600, tags=[...], vary_on=[...])` |
| Manual signal + `cache.delete()` | `ModelTagManager.register_model(Model)` |
