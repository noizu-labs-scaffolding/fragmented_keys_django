# Architecture Summary

Django integration (v0.2.0) for `fragmented-keys` — tag-versioned cache invalidation where incrementing a tag version automatically invalidates all composite keys containing that tag.

## Components

- **DjangoCacheHandler** — Adapts Django cache API to `fragmented_keys.CacheHandler` protocol (by alias name or by cache instance)
- **FragmentedKeysCacheBackend** — Drop-in Django `BaseCache` subclass; delegation mode (`CACHE_NAME`) or standalone mode (`LOCATION`). Provides `*_with_tags` methods and `create_key_ring()`.
- **@tagged_cache / @cached_async** — Decorators that build composite cache keys from tag templates + `vary_on` params
- **ModelTagManager** — Auto-increments tags on `post_save`/`post_delete` via Django signals. Also provides `invalidate_scope()`, `invalidate_bulk()`, `invalidate_model_tag()`.
- **CacheAwareManager / CacheAwareQuerySet** — Fires tag invalidation on `bulk_create`, `bulk_update`, `QS.delete()`, `QS.update()` (operations that bypass Django signals)
- **KeyRing Registry** — Global named registry for `FragmentedKeyRing` instances: `register_key_ring()`, `get_key_ring()`, `clear_key_rings()`
- **Tag factories** — `model_tag()`, `list_tag()`, `aggregate_tag()`, `constant_tag()`, `custom_tag()` plus template parsing and resolution utilities
- **config.py** — `configure_fragmented_keys()` for one-call global setup in `AppConfig.ready()` (handler + prefix + default KeyRing). Also `reset_configuration()`, `get_cache_handler()`, `set_cache_handler_globally()`, `set_global_prefix()`, `get_global_prefix()`.

## Three Usage Modes

1. **Decorator mode**: `@tagged_cache(tags=[...], vary_on=[...])` on individual functions (sync or async)
2. **Backend mode**: Set `FragmentedKeysCacheBackend` as `CACHES["BACKEND"]`, use `*_with_tags` methods directly
3. **KeyRing mode**: Define key templates centrally in `AppConfig.ready()`, retrieve in views via `get_key_ring()`

## Backend Configuration Modes

1. **Delegation**: `CACHE_NAME` points to an existing `CACHES` alias — shares connection pool, works with LocMemCache for tests
2. **Standalone**: `LOCATION` provides connection URL directly — single config entry, instantiates `BACKEND_CLASS` (default: `django.core.cache.backends.redis.RedisCache`)

## Invalidation Flow

Cache keys embed current tag versions. When a model changes, `ModelTagManager` increments the tag version via `StandardTag.increment()`. Next cache read composes a different key string → cache miss → recompute. No explicit delete needed.

For bulk operations (`bulk_create`, `bulk_update`, `QS.delete()`, `QS.update()`), `CacheAwareManager` wraps these to fire lifecycle hooks since Django signals are not emitted.

## Observability

No built-in telemetry. Subclass `FragmentedKeysCacheBackend` and override `_build_tagged_key` (tag version reads) and `invalidate_tags` (tag version writes) for metrics/tracing. See `docs/usage/telemetry.rst`.

## Stack

Python 3.11+ · Django 5.0+ · fragmented-keys >= 0.1.3 · pytest (~270 tests) · Sphinx · django-redis (optional)
