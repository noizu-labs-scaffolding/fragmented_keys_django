# Data Flow

## Cache Read (via `@tagged_cache`)

```mermaid
sequenceDiagram
    participant C as Caller
    participant D as @tagged_cache
    participant T as StandardTag
    participant K as StandardKey
    participant H as DjangoCacheHandler
    participant R as Redis

    C->>D: call decorated function
    D->>T: parse tag templates, create StandardTag instances
    D->>K: StandardKey(name, tags)
    K->>T: read current version for each tag
    T->>H: get(tag_version_key)
    H->>R: cache.get()
    R-->>H: version string (or None → "0")
    H-->>T: version
    T-->>K: version
    K-->>D: composite key string (e.g. "NOZ:User:42:v3:Dashboard:v1:fn_name")
    D->>H: cache.get(composite_key)
    H->>R: get
    alt cache hit
        R-->>D: cached result
        D-->>C: return result
    else cache miss
        D->>C: execute original function
        C-->>D: computed result
        D->>H: cache.set(composite_key, result, timeout)
        H->>R: set
        D-->>C: return result
    end
```

## Cache Invalidation (via signals)

```mermaid
sequenceDiagram
    participant M as Model.save() / .delete()
    participant S as Django Signal (post_save/post_delete)
    participant MTM as ModelTagManager
    participant T as StandardTag
    participant H as DjangoCacheHandler
    participant R as Redis

    M->>S: emit signal
    S->>MTM: _on_model_change(sender, instance)
    MTM->>T: StandardTag(model_name, str(pk))
    MTM->>T: tag.increment()
    T->>H: get(tag_version_key)
    H->>R: get current version
    R-->>H: "3"
    T->>H: set(tag_version_key, "4")
    H->>R: set new version
    Note over R: Old composite keys now<br/>resolve to different strings →<br/>cache miss on next read
```

## Key Composition

A `StandardKey` produces its cache key string by concatenating:

1. Global prefix (e.g. `NOZ`)
2. For each tag: `{tag_name}:{instance}:v{current_version}`
3. Base key name (function qualified name + vary_on params)

When any tag's version increments, the composed string changes, and the old cached value is never found again (it expires naturally via TTL).

## DjangoCacheHandler Adapter

`DjangoCacheHandler` implements the `fragmented_keys.CacheHandler` protocol:

| Protocol method | Django cache call | Notes |
|----------------|-------------------|-------|
| `get(key)` | `cache.get(key)` | Coerces result to `str` (handles bytes, dict, int) |
| `set(key, value, ttl)` | `cache.set(key, value, timeout=ttl)` | |
| `get_multi(keys)` | `cache.get_many(keys)` | Returns `dict[str, str]`, omits misses |

### Two construction modes

```mermaid
flowchart TD
    A{Config has LOCATION?} -->|Yes| B[Standalone mode]
    A -->|No| C{Config has CACHE_NAME?}
    C -->|Yes| D[Delegation mode]
    C -->|No| E["Delegation mode<br/>(default → 'default')"]

    B --> F["import_string(BACKEND_CLASS)<br/>instantiate backend(LOCATION, params)"]
    F --> G["DjangoCacheHandler(cache=instance)"]

    D --> H["DjangoCacheHandler(cache_name)"]
    E --> H

    G --> I["Configuration.set_default_cache_handler()"]
    H --> I
```

- **Delegation**: `DjangoCacheHandler("default")` → `caches["default"]` → shares the existing connection pool and config
- **Standalone**: `DjangoCacheHandler(cache=underlying)` → wraps a backend instance created by `FragmentedKeysCacheBackend.__init__` — no Django alias required

Both paths converge: `self._handler` is set, and all tag-aware methods use it identically.

## Telemetry Instrumentation Points

The library emits no metrics/logs by default. Subclass the backend to add observability:

| Hook | What it captures | Redis I/O |
|------|-----------------|-----------|
| `_build_tagged_key(key, tags, group_id)` | Tag version **reads** during key composition | 1 GET per tag |
| `invalidate_tags(tags)` | Tag version **writes** during invalidation | 1 SET per tag |
| `get_with_tags` / `set_with_tags` | Cache hit/miss, overall latency | 1 GET or SET for the data |

See `docs/usage/telemetry.rst` for StatsD, Prometheus, and OpenTelemetry examples.
