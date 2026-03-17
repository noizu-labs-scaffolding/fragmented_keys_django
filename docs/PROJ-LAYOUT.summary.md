# Project Layout (Summary)

```
fragmented_keys_django/
├── fragmented_keys_django/         # Package source
│   ├── cache_backends/             #   Django cache backend + handler adapter
│   ├── cache_utils/                #   Decorators, model helpers, tag factories
│   ├── __init__.py
│   └── config.py                   #   Global configuration helpers
├── tests/                          # Pytest suite (144 tests, 99% coverage)
│   ├── test_backend.py             #     Backend: delegation, standalone, tag-aware
│   ├── test_config.py              #     Configuration functions
│   ├── test_decorators.py          #     @tagged_cache + @cached_async
│   ├── test_handlers.py            #     DjangoCacheHandler type conversions
│   ├── test_model_helpers.py       #     ModelTagManager signals + exceptions
│   └── test_tags.py                #     Tag factory utilities
├── docs/                           # Sphinx documentation
│   ├── usage/                      #   Guides: decorator, backend, tags, testing, telemetry
│   ├── api/                        #   API reference (autodoc)
│   ├── arch/                       #   Architecture details (data-flow diagrams)
│   └── conf.py                     #   Sphinx config
├── .python-version                 # Python 3.11
├── .readthedocs.yaml               # RTD build config
├── pyproject.toml                  # Package metadata and dependencies
├── CLAUDE.md                       # Agent instructions
├── EXAMPLES.md                     # Usage examples
├── MIGRATION.md                    # Migration guide
├── README.md                       # Project overview
└── uv.lock                         # Lockfile
```
