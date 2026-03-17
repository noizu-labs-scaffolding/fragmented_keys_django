# Project Layout

```
fragmented_keys_django/
├── fragmented_keys_django/         # Package source code
│   ├── cache_backends/             #   Django cache backend integration
│   │   ├── __init__.py             #     Exports DjangoCacheHandler, FragmentedKeysCacheBackend
│   │   ├── django_backend.py       #     BaseCache subclass with tag-based invalidation (delegation + standalone modes)
│   │   └── handlers.py             #     Adapter: Django cache <-> fragmented_keys CacheHandler protocol
│   ├── cache_utils/                #   High-level utilities (decorators, helpers, tag factories)
│   │   ├── __init__.py             #     Exports tagged_cache, ModelTagManager, tag factories
│   │   ├── decorators.py           #     @tagged_cache and @cached_async decorators
│   │   ├── model_helpers.py        #     ModelTagManager — auto-invalidation via Django signals
│   │   └── tags.py                 #     Tag factories: model_tag, list_tag, aggregate_tag
│   ├── __init__.py                 #   Package version (__version__)
│   └── config.py                   #   configure_fragmented_keys(), handler/prefix helpers
├── tests/                          # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py                 #   Fixtures, Django settings for tests (LocMemCache)
│   ├── test_backend.py             #   Tests for FragmentedKeysCacheBackend (delegation, standalone, tag-aware)
│   ├── test_config.py              #   Tests for config.py functions
│   ├── test_decorators.py          #   Tests for @tagged_cache and @cached_async
│   ├── test_handlers.py            #   Tests for DjangoCacheHandler (type conversions, dual init)
│   ├── test_model_helpers.py       #   Tests for ModelTagManager (signals, invalidation, exceptions)
│   └── test_tags.py                #   Tests for tag factory utilities
├── docs/                           # Sphinx documentation
│   ├── index.rst                   #   Root toctree
│   ├── quickstart.rst              #   Quick-start guide
│   ├── conf.py                     #   Sphinx configuration
│   ├── requirements.txt            #   Docs build dependencies
│   ├── usage/                      #   Usage guides
│   │   ├── index.rst               #     Usage toctree (decorator, backend, tags, testing, telemetry)
│   │   ├── decorator.rst           #     @tagged_cache usage
│   │   ├── backend.rst             #     FragmentedKeysCacheBackend usage (delegation + standalone)
│   │   ├── tags.rst                #     Tag factories and templates
│   │   ├── testing.rst             #     Testing patterns
│   │   └── telemetry.rst           #     Observability: logging, StatsD, Prometheus, OpenTelemetry
│   ├── api/                        #   API reference (autodoc)
│   │   ├── index.rst               #     API toctree
│   │   ├── backends.rst            #     FragmentedKeysCacheBackend API
│   │   ├── config.rst              #     Configuration API
│   │   ├── decorators.rst          #     Decorator API
│   │   ├── model_helpers.rst       #     ModelTagManager API
│   │   └── tags.rst                #     Tag utilities API
│   ├── arch/                       #   Architecture details
│   │   └── data-flow.md            #     Sequence diagrams (Mermaid)
│   ├── changelog.rst               #   Release changelog
│   ├── migration.md                #   Migration guide
│   ├── fragmented-cache-concepts.md #  Conceptual overview of fragmented key caching
│   ├── PROJ-ARCH.md                #   Architecture document
│   ├── PROJ-ARCH.summary.md        #   Architecture summary (agent context)
│   ├── PROJ-LAYOUT.md              #   This file
│   └── PROJ-LAYOUT.summary.md      #   Abbreviated tree (agent context)
├── dist/                           # Built package artifacts (.whl, .tar.gz)
├── .python-version                 # Python 3.11 (pyenv / uv)
├── .readthedocs.yaml               # Read the Docs build configuration
├── .gitignore                      # Standard Python gitignore
├── CLAUDE.md                       # Claude Code agent instructions
├── EXAMPLES.md                     # Usage examples
├── MIGRATION.md                    # Migration guide
├── README.md                       # Project overview and quick-start
├── pyproject.toml                  # Package metadata, deps (Django 5.0.3, django-redis, fragmented-keys)
├── setup.py                        # Setuptools shim
└── uv.lock                         # uv lockfile
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fragmented-keys>=0.1.3` | Core library — tag versioning and fragmented key logic |
| `django==5.0.3` | Web framework providing cache framework and signals |
| `django-redis==6.0.0` | Redis cache backend for Django |

## Key Files Requiring Setup

| File | Action |
|------|--------|
| `.python-version` | Ensures Python 3.11 via pyenv/uv |
| Django settings | Must call `configure_fragmented_keys()` in `AppConfig.ready()` or configure `CACHES` |
