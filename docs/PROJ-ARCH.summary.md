# Architecture Summary

Django integration for `fragmented-keys` — tag-versioned cache invalidation where incrementing a tag version automatically invalidates all composite keys containing that tag.

## Components

- **DjangoCacheHandler** — Adapts Django cache API to `fragmented_keys.CacheHandler` protocol (by alias name or by cache instance)
- **FragmentedKeysCacheBackend** — Drop-in Django `BaseCache` subclass; delegation mode (`CACHE_NAME`) or standalone mode (`LOCATION`)
- **@tagged_cache / @cached_async** — Decorators that build composite cache keys from tag templates + `vary_on` params
- **ModelTagManager** — Auto-increments tags on `post_save`/`post_delete` via Django signals
- **Tag factories** — `model_tag()`, `list_tag()`, `aggregate_tag()` convenience constructors
- **config.py** — `configure_fragmented_keys()` for one-call global setup in `AppConfig.ready()`

## Two Usage Modes

1. **Backend mode**: Set `FragmentedKeysCacheBackend` as `CACHES["BACKEND"]` for transparent tag-based invalidation
2. **Decorator mode**: Use `@tagged_cache(tags=[...], vary_on=[...])` on individual functions (sync or async)

## Backend Configuration Modes

1. **Delegation**: `CACHE_NAME` points to an existing `CACHES` alias — shares connection pool, works with LocMemCache for tests
2. **Standalone**: `LOCATION` provides connection URL directly — single config entry, instantiates `BACKEND_CLASS` (default: `django.core.cache.backends.redis.RedisCache`)

## Invalidation Flow

Cache keys embed current tag versions. When a model changes, `ModelTagManager` increments the tag version via `StandardTag.increment()`. Next cache read composes a different key string → cache miss → recompute. No explicit delete needed.

## Observability

No built-in telemetry. Subclass `FragmentedKeysCacheBackend` and override `_build_tagged_key` (tag version reads) and `invalidate_tags` (tag version writes) for metrics/tracing. See `docs/usage/telemetry.rst`.

## Stack

Python 3.11+ · Django 5.0+ · fragmented-keys >= 0.1.3 · pytest · Sphinx · django-redis (optional)
