# Project Layout

```
fragmented_keys_django/
├── fragmented_keys_django/         # Package source code
│   ├── cache_backends/             #   Django cache backend integration
│   │   ├── __init__.py             #     Exports DjangoCacheHandler, FragmentedKeysCacheBackend
│   │   ├── django_backend.py       #     BaseCache subclass with tag-based invalidation
│   │   └── handlers.py            #     Adapter: Django cache <-> fragmented_keys CacheHandler protocol
│   ├── cache_utils/                #   High-level utilities (decorators, helpers, tag factories)
│   │   ├── __init__.py             #     Exports tagged_cache, ModelTagManager, tag factories
│   │   ├── decorators.py           #     @tagged_cache view/function decorator
│   │   ├── model_helpers.py        #     ModelTagManager — auto-invalidation via Django signals
│   │   └── tags.py                 #     Tag factories: model_tag, list_tag, aggregate_tag
│   ├── __init__.py                 #   Package version (__version__)
│   └── config.py                   #   configure_fragmented_keys(), handler/prefix helpers
├── tests/                          # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py                 #   Fixtures, Django settings for tests
│   ├── test_backend.py             #   Tests for FragmentedKeysCacheBackend
│   ├── test_decorators.py          #   Tests for @tagged_cache
│   ├── test_handlers.py            #   Tests for DjangoCacheHandler
│   ├── test_model_helpers.py       #   Tests for ModelTagManager
│   └── test_tags.py                #   Tests for tag factory utilities
├── docs/                           # Documentation
│   ├── PROJ-LAYOUT.md              #   This file
│   └── PROJ-LAYOUT.summary.md     #   Abbreviated tree for agent context
├── .python-version                 # Python 3.11 (pyenv / uv)
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
| Django settings | Must call `configure_fragmented_keys()` in `AppConfig.ready()` or settings |
