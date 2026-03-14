# What Are Fragmented (Versioned-Tag) Caches?

Fragmented caching is a cache invalidation strategy where **keys are never
explicitly deleted**. Instead, each cache key embeds the current version of
every tag it depends on. When underlying data changes, a tag's version is
incremented — and the next read composes a *different* key string, producing a
natural cache miss. The old entry is never touched; it simply expires via its
TTL.

This page explains the concept from the ground up before you look at any code.

---

## The Problem with Traditional Cache Invalidation

In a typical Django project, caching looks like this:

```python
# Write
cache.set(f"user_profile_{user_id}", profile_data, timeout=3600)

# Invalidate
@receiver(post_save, sender=User)
def on_user_save(sender, instance, **kwargs):
    cache.delete(f"user_profile_{instance.pk}")
    cache.delete(f"user_dashboard_{instance.pk}")
    cache.delete(f"user_donations_{instance.pk}")
    # ... did you remember them all?
```

This creates three recurring problems:

1. **Fragile key tracking** — Every place that *writes* a key must have a
   matching *delete* somewhere else. Miss one and you serve stale data.
2. **Cascading deletes** — A single model change may require deleting dozens of
   keys across unrelated modules. The signal handler becomes a god-object that
   knows about every cache consumer.
3. **Orphan keys** — If you rename or remove a cache call but forget the
   corresponding delete, dead keys accumulate.

---

## How Fragmented Keys Solve This

### Tags and Versions

A **tag** is a named counter stored in the same cache backend. It has two
parts:

| Part | Example | Purpose |
|------|---------|---------|
| **Name** | `User` | Identifies the kind of dependency |
| **Instance** | `42` | Scopes the tag to a specific record |

Together they form a tag like `User:42`. The cache backend stores its current
**version** — an integer that starts at `1` and only ever goes up.

### Composite Keys

When you cache a value, the library builds a **composite key** by concatenating:

```
base_name + tag1_name + tag1_instance + tag1_version + tag2_name + ...
```

For example, a function `get_dashboard(user_id=42)` with tags
`['Dashboard', 'User:42']` might produce:

```
get_dashboard_Dashboard__v3_User_42_v17
```

The key *embeds* the current version of every tag at write time.

### Invalidation by Version Bump

When `User(pk=42)` is saved, the system increments the version of tag
`User:42` from `17` to `18`. The next read of `get_dashboard(user_id=42)`
composes:

```
get_dashboard_Dashboard__v3_User_42_v18
```

That key doesn't exist in the cache — **cache miss**. The function recomputes,
and the new result is stored under the new key. The old entry
(`...User_42_v17`) is never deleted; it expires naturally when its TTL runs
out.

### What This Means in Practice

- **No explicit deletes.** You never call `cache.delete()`.
- **No key tracking.** You don't need a registry of "all keys that depend on
  User 42".
- **No orphan keys.** Old entries expire via TTL. Changing or removing a cache
  call doesn't leave dead invalidation code behind.
- **Surgical invalidation.** Saving `User(pk=42)` only affects caches that
  include the `User:42` tag. `User:7`, `User:100`, etc. are untouched.

---

## Tag Scopes

Tags come in two scopes, and the distinction matters:

### Instance-Scoped Tags

```
User:{user_id}    →  User:42
Campaign:{id}     →  Campaign:7
```

The placeholder is resolved from function arguments at call time. Saving
`User(pk=42)` increments `User:42` only — cache entries for other users are
unaffected.

**Use for:** anything tied to a specific database record.

### Global Tags

```
Dashboard
APIConfig
```

No placeholder, so every call to the decorated function shares the same tag.
Incrementing a global tag invalidates *all* cached results of functions that
use it, regardless of arguments.

**Use for:** config-level or site-wide data where any change should bust the
entire cache for that concern.

---

## How `vary_on` Differs from Tags

These two parameters are often confused but serve different purposes:

| | `tags` | `vary_on` |
|---|---|---|
| **Purpose** | Controls *when* cache entries are invalidated | Controls *which argument combinations* get separate cache entries |
| **Stored where** | As versioned counters in the cache backend | Embedded directly in the key string |
| **Example** | `tags=['User:{user_id}']` | `vary_on=['user_id', 'page']` |

Consider:

```python
@tagged_cache(
    tags=['User:{user_id}'],
    vary_on=['user_id', 'page']
)
def get_user_feed(user_id, page):
    ...
```

- `vary_on` ensures `get_user_feed(42, 1)` and `get_user_feed(42, 2)` have
  **different cache entries** (different pages).
- `tags` ensures that when `User(pk=42)` is saved, **both** page 1 and page 2
  are invalidated (because both embed `User:42`'s version).

Without `vary_on`, all argument combinations would share one cache entry.
Without `tags`, no automatic invalidation would occur.

---

## Lifecycle of a Cached Value

```
1. Function called with (user_id=42, page=1)
2. Library looks up current version of each tag:
     User:42  → version 17
3. Composes cache key:
     "get_user_feed_user_id_42_page_1_User_42_v17"
4. Checks cache:
     MISS → calls function, stores result under that key with TTL
     HIT  → returns cached value

--- later, User 42 is saved ---

5. ModelTagManager signal increments User:42 → version 18
6. Next call to get_user_feed(42, 1) composes:
     "get_user_feed_user_id_42_page_1_User_42_v18"
7. Cache MISS → recomputes, stores under new key
8. Old key (...v17) expires naturally via TTL
```

---

## Tag Factory Functions

The library provides semantic constructors that all create the same underlying
`StandardTag` object. They exist to make intent clear in your code:

| Factory | Intended Use | Example |
|---------|-------------|---------|
| `model_tag('User', 42)` | Cache tied to a single model instance | User profile, user settings |
| `list_tag('Donations', 42)` | Cache of a query/list scoped to an owner | "User 42's donation history" |
| `aggregate_tag('Stats', 'daily_42')` | Computed statistics or rollups | Dashboard aggregations |
| `custom_tag('Weather', 'NYC_2024')` | Anything that doesn't fit the above | External data, feature flags |

Under the hood, `model_tag('User', 42)` and `list_tag('User', 42)` produce
identical `StandardTag('User', '42')` objects. The different names are a
readability convention, not a functional difference.

---

## Comparison with Other Approaches

| Strategy | Deletes required? | Tracks keys? | Orphan risk | Granularity |
|----------|:-:|:-:|:-:|---|
| Manual `cache.delete()` | Yes | You do it | High | Per-key |
| Cache generation/epoch | No | No | Low | All-or-nothing |
| Django `cache.clear()` | N/A | No | None | Nuclear — everything |
| **Fragmented keys** | **No** | **No** | **None (TTL)** | **Per-tag-instance** |

---

## When NOT to Use Fragmented Keys

- **Extremely short TTLs (< 10s)** — The overhead of tag version lookups may
  exceed the benefit when data is nearly live anyway.
- **Write-heavy, read-light paths** — If a tag is incremented more often than
  it's read, you're paying for version bumps that never serve a cache hit.
- **Cache entries with no natural invalidation trigger** — If there's no event
  that should bust the cache (e.g., random external data polled on a timer),
  a simple TTL-only approach is simpler.
