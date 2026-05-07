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

## Cache Invalidation (via bulk operations)

```mermaid
sequenceDiagram
    participant C as Caller
    participant QS as CacheAwareQuerySet
    participant DB as Database
    participant MTM as ModelTagManager
    participant T as StandardTag
    participant H as DjangoCacheHandler
    participant R as Redis

    C->>QS: .filter(org_id=42).delete()
    QS->>DB: SELECT pk FROM model WHERE org_id=42
    DB-->>QS: [pk1, pk2, pk3]
    QS->>DB: DELETE FROM model WHERE org_id=42
    DB-->>QS: (3, {"app.Model": 3})
    loop For each pk
        QS->>MTM: _fire_lifecycle("delete", model, FakePKInstance(pk))
        MTM->>T: tag.increment()
        T->>H: set(tag_version_key, new_version)
        H->>R: set
    end
    QS-->>C: (3, {"app.Model": 3})
```

## KeyRing Flow (define once, use everywhere)

```mermaid
sequenceDiagram
    participant App as AppConfig.ready()
    participant CFG as configure_fragmented_keys()
    participant REG as KeyRing Registry
    participant FKR as FragmentedKeyRing

    App->>CFG: configure_fragmented_keys(prefix="NOZ")
    CFG->>FKR: FragmentedKeyRing(handlers, prefix)
    CFG->>REG: register_key_ring("default", ring)

    Note over App: Define key templates
    App->>REG: get_key_ring("default")
    REG-->>App: ring
    App->>FKR: ring.define_key("org_list", ["organization", "category", "review"])
```

```mermaid
sequenceDiagram
    participant V as View
    participant REG as KeyRing Registry
    participant FKR as FragmentedKeyRing
    participant K as Key Object
    participant H as DjangoCacheHandler
    participant R as Redis

    V->>REG: get_key_ring("default")
    REG-->>V: ring
    V->>FKR: ring.get_org_list_key_obj("cat:education", "__all__", "cat:education")
    FKR-->>V: key object
    V->>K: key.get_key_str()
    K->>H: read tag versions
    H->>R: get_many(tag_keys)
    R-->>H: versions
    H-->>K: versions
    K-->>V: "NOZ:organization:cat:education:v2:category:__all__:v1:review:cat:education:v3:org_list"
    V->>H: cache.get(composite_key)
    H->>R: get
    R-->>V: cached result or miss
```

## Backend *_with_tags Flow

```mermaid
sequenceDiagram
    participant V as View
    participant FB as FragmentedKeysCacheBackend
    participant SK as StandardKey
    participant T as Tags
    participant H as DjangoCacheHandler
    participant R as Redis

    V->>FB: get_or_set_with_tags("profile", loader, [("User", "42")], timeout=3600)
    FB->>FB: _normalize_tags([("User", "42")])
    FB->>T: StandardTag("User", "42")
    FB->>SK: StandardKey("profile", [tag])
    FB->>FB: _build_tagged_key("profile", [tag])
    SK->>T: read tag versions
    T->>H: get(version_key)
    H->>R: get
    R-->>FB: composite key string
    FB->>H: cache.get(composite_key)
    H->>R: get
    alt cache hit
        R-->>V: cached result
    else cache miss
        FB->>V: call loader()
        V-->>FB: computed result
        FB->>H: cache.set(composite_key, result, 3600)
        H->>R: set
        FB-->>V: computed result
    end
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

## Configuration Initialization

```mermaid
flowchart TD
    A["configure_fragmented_keys()<br/>(AppConfig.ready)"] --> B{Existing handler?}
    B -->|Yes: recursion guard| C[Reuse existing handler]
    B -->|No| D["Create DjangoCacheHandler(cache_name)"]
    D --> E["Configuration.set_default_cache_handler()"]
    C --> F["Configuration.set_global_prefix()"]
    E --> F
    F --> G{setup_key_ring?}
    G -->|Yes| H["Create FragmentedKeyRing"]
    H --> I["register_key_ring('default', ring)"]
    G -->|No| J[Done]
    I --> J
```

## Telemetry Instrumentation Points

The library emits no metrics/logs by default. Subclass the backend to add observability:

| Hook | What it captures | Redis I/O |
|------|-----------------|-----------|
| `_build_tagged_key(key, tags, group_id)` | Tag version **reads** during key composition | 1 GET per tag |
| `invalidate_tags(tags)` | Tag version **writes** during invalidation | 1 SET per tag |
| `get_with_tags` / `set_with_tags` | Cache hit/miss, overall latency | 1 GET or SET for the data |

See `docs/usage/telemetry.rst` for StatsD, Prometheus, and OpenTelemetry examples.
