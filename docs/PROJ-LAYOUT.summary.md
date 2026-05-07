# Project Layout (Summary)

```
fragmented_keys_django/                 # v0.2.0
├── fragmented_keys_django/             # Package source
│   ├── cache_backends/                 #   Django cache backend + handler adapter
│   │   ├── django_backend.py           #     BaseCache subclass (delegation + standalone)
│   │   └── handlers.py                 #     Django ↔ fragmented_keys CacheHandler bridge
│   ├── cache_utils/                    #   Decorators, model helpers, tag factories, bulk ops
│   │   ├── bulk.py                     #     CacheAwareManager/QuerySet — bulk op invalidation
│   │   ├── decorators.py              #     @tagged_cache + @cached_async
│   │   ├── key_rings.py               #     Global KeyRing registry for key templates
│   │   ├── model_helpers.py           #     ModelTagManager — signal-driven invalidation
│   │   └── tags.py                    #     model_tag, list_tag, aggregate_tag factories
│   ├── __init__.py                     #   Version + top-level exports
│   └── config.py                       #   configure_fragmented_keys() setup helper
├── tests/                              # Pytest suite (~270 tests)
│   ├── conftest.py                     #   Fixtures + Django test settings
│   ├── test_backend.py                 #   Backend: delegation, standalone, tag-aware (56)
│   ├── test_bulk.py                    #   Bulk ops invalidation (4)
│   ├── test_config.py                  #   Configuration functions (16)
│   ├── test_decorators.py             #   @tagged_cache + @cached_async (39)
│   ├── test_handlers.py               #   Handler type conversions (21)
│   ├── test_integration.py            #   Live Redis end-to-end (50, requires Redis)
│   ├── test_key_rings.py             #   KeyRing registry (5)
│   ├── test_model_helpers.py          #   ModelTagManager signals (40)
│   └── test_tags.py                   #   Tag factories (42)
├── docs/                               # Sphinx docs (RTD-hosted)
│   ├── usage/                          #   Guides: decorator, backend, tags, testing, telemetry
│   ├── api/                            #   API reference (autodoc)
│   ├── arch/                           #   Architecture details (data-flow diagrams)
│   ├── _django_settings.py            #   Minimal settings for autodoc builds
│   └── conf.py                         #   Sphinx config
├── .python-version                     # Python 3.11
├── .readthedocs.yaml                   # RTD build config
├── pyproject.toml                      # Package metadata and dependencies
├── CLAUDE.md                           # Agent instructions
├── EXAMPLES.md                         # Usage examples
├── MIGRATION.md                        # Migration guide
├── README.md                           # Project overview
├── setup.py                            # Setuptools shim
└── uv.lock                             # Lockfile
```
