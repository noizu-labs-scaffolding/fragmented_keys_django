# Project Layout

```
fragmented_keys_django/                 # Repository root (v0.2.0)
├── fragmented_keys_django/             # Package source code
│   ├── cache_backends/                 #   Django cache backend integration
│   │   ├── __init__.py                 #     Exports DjangoCacheHandler, FragmentedKeysCacheBackend
│   │   ├── django_backend.py           #     BaseCache subclass with tag-based invalidation (delegation + standalone modes)
│   │   └── handlers.py                 #     Adapter: Django cache <-> fragmented_keys CacheHandler protocol
│   ├── cache_utils/                    #   High-level utilities (decorators, helpers, tag factories)
│   │   ├── __init__.py                 #     Exports tagged_cache, ModelTagManager, tag factories, CacheAwareManager
│   │   ├── bulk.py                     #     CacheAwareManager/QuerySet — fires tag invalidation on bulk_create/update/delete
│   │   ├── decorators.py              #     @tagged_cache and @cached_async decorators
│   │   ├── key_rings.py               #     Global KeyRing registry — define/retrieve key templates via get_key_ring()
│   │   ├── model_helpers.py           #     ModelTagManager — auto-invalidation via Django signals
│   │   └── tags.py                    #     Tag factories: model_tag, list_tag, aggregate_tag
│   ├── __init__.py                     #   Package version (__version__), top-level exports
│   └── config.py                       #   configure_fragmented_keys(), handler/prefix helpers
├── tests/                              # Pytest test suite (~270 tests)
│   ├── __init__.py
│   ├── conftest.py                     #   Fixtures, Django settings for tests (LocMemCache)
│   ├── test_backend.py                 #   FragmentedKeysCacheBackend (delegation, standalone, tag-aware) — 56 tests
│   ├── test_bulk.py                    #   CacheAwareManager/QuerySet bulk ops invalidation — 4 tests
│   ├── test_config.py                  #   config.py functions — 16 tests
│   ├── test_decorators.py             #   @tagged_cache and @cached_async — 39 tests
│   ├── test_handlers.py               #   DjangoCacheHandler (type conversions, dual init) — 21 tests
│   ├── test_integration.py            #   Redis integration tests (requires localhost:6379, db 15) — 50 tests
│   ├── test_key_rings.py             #   KeyRing registry (register, get, clear) — 5 tests
│   ├── test_model_helpers.py          #   ModelTagManager (signals, invalidation, exceptions) — 40 tests
│   └── test_tags.py                   #   Tag factory utilities — 42 tests
├── docs/                               # Sphinx documentation (RTD-hosted)
│   ├── _static/                        #   Static assets for Sphinx theme
│   │   └── .gitkeep
│   ├── _django_settings.py            #   Minimal Django settings for Sphinx autodoc builds
│   ├── index.rst                       #   Root toctree
│   ├── quickstart.rst                 #   Quick-start guide
│   ├── conf.py                         #   Sphinx configuration
│   ├── requirements.txt               #   Docs build dependencies
│   ├── usage/                          #   Usage guides
│   │   ├── index.rst                   #     Usage toctree (decorator, backend, tags, testing, telemetry)
│   │   ├── decorator.rst              #     @tagged_cache usage
│   │   ├── backend.rst                #     FragmentedKeysCacheBackend usage (delegation + standalone)
│   │   ├── tags.rst                   #     Tag factories and templates
│   │   ├── testing.rst               #     Testing patterns
│   │   └── telemetry.rst             #     Observability: logging, StatsD, Prometheus, OpenTelemetry
│   ├── api/                            #   API reference (autodoc)
│   │   ├── index.rst                   #     API toctree
│   │   ├── backends.rst               #     FragmentedKeysCacheBackend API
│   │   ├── config.rst                 #     Configuration API
│   │   ├── decorators.rst             #     Decorator API
│   │   ├── model_helpers.rst          #     ModelTagManager API
│   │   └── tags.rst                   #     Tag utilities API
│   ├── arch/                           #   Architecture details
│   │   └── data-flow.md               #     Sequence diagrams (Mermaid)
│   ├── changelog.rst                  #   Release changelog
│   ├── migration.md                   #   Migration guide (Sphinx-linked)
│   ├── fragmented-cache-concepts.md   #   Conceptual overview of fragmented key caching
│   ├── PROJ-ARCH.md                   #   Architecture document (agent context)
│   ├── PROJ-ARCH.summary.md           #   Architecture summary (agent context)
│   ├── PROJ-LAYOUT.md                 #   This file
│   └── PROJ-LAYOUT.summary.md        #   Abbreviated tree (agent context)
├── .python-version                     # Python 3.11 (pyenv / uv)
├── .readthedocs.yaml                   # Read the Docs build configuration
├── .gitignore                          # Standard Python gitignore
├── CLAUDE.md                           # Claude Code agent instructions
├── EXAMPLES.md                         # Usage examples
├── MIGRATION.md                        # Migration guide (root copy)
├── README.md                           # Project overview and quick-start
├── pyproject.toml                      # Package metadata, deps (Django 5.0+, fragmented-keys; django-redis optional)
├── setup.py                            # Setuptools shim
└── uv.lock                             # uv lockfile (deterministic builds)
```

## Module Map

| Module | Public API | Purpose |
|--------|-----------|---------|
| `cache_backends.django_backend` | `FragmentedKeysCacheBackend` | Drop-in `BaseCache` subclass; delegation or standalone mode |
| `cache_backends.handlers` | `DjangoCacheHandler` | Bridges Django cache API ↔ fragmented_keys `CacheHandler` protocol |
| `cache_utils.bulk` | `CacheAwareManager`, `CacheAwareQuerySet` | Fires tag invalidation on `bulk_create`/`bulk_update`/`QS.delete()`/`QS.update()` |
| `cache_utils.decorators` | `tagged_cache`, `cached_async` | Function/method cache decorators with tag dependencies |
| `cache_utils.key_rings` | `register_key_ring`, `get_key_ring`, `clear_key_rings` | Global named `FragmentedKeyRing` registry for key templates |
| `cache_utils.model_helpers` | `ModelTagManager` | Auto-invalidation via Django `post_save`/`post_delete` signals |
| `cache_utils.tags` | `model_tag`, `list_tag`, `aggregate_tag` | Tag factory functions for common patterns |
| `config` | `configure_fragmented_keys` | One-call setup: handler, prefix, backend wiring |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fragmented-keys>=0.1.3` | Core library — tag versioning and fragmented key logic |
| `django>=5.0` | Web framework providing cache framework and signals |
| `django-redis` (optional) | Third-party Redis backend with extras (compression, sentinel, sessions) |

## Key Files Requiring Setup

| File | Action |
|------|--------|
| `.python-version` | Ensures Python 3.11 via pyenv/uv |
| Django settings | Must call `configure_fragmented_keys()` in `AppConfig.ready()` or configure `CACHES` |

## Test Organization

| File | Scope | Notes |
|------|-------|-------|
| `test_backend.py` | Backend modes, tag ops, TTL, key versioning | Largest suite (56 tests) |
| `test_integration.py` | End-to-end against live Redis | Requires `localhost:6379` db 15; skipped without Redis |
| `test_model_helpers.py` | Signal wiring, lifecycle hooks, exceptions | 40 tests |
| `test_decorators.py` | Sync + async decorator behavior | 39 tests |
| `test_tags.py` | Tag factory correctness | 42 tests |
| `test_handlers.py` | Handler type conversions, dual init | 21 tests |
| `test_config.py` | Configuration helpers | 16 tests |
| `test_key_rings.py` | Registry CRUD | 5 tests |
| `test_bulk.py` | Bulk operation invalidation | 4 tests |
