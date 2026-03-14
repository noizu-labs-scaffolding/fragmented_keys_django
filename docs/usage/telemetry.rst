Telemetry & Observability
=========================

fragmented-keys-django is **observability-dark by default** — no logging, no
metrics, no tracing.  This is intentional: the library sits in the hot path
(every cache read resolves tag versions) and should not impose a telemetry
stack.  Instead it exposes clear instrumentation points so you can wire in
whatever you already run.

This guide covers four layers, from least to most invasive:

1. `Python logging`_ — structured logs for debugging and audit trails
2. `Metrics (StatsD / Prometheus)`_ — counters, gauges, histograms
3. `Distributed tracing (OpenTelemetry)`_ — spans across cache operations
4. `Django signals for custom hooks`_ — react to invalidation events


Python logging
--------------

The cheapest starting point.  Add loggers to the two hot paths: the decorator
wrapper and the signal handler.

**Decorator hit/miss logging:**

.. code-block:: python

   # myapp/instrumentation.py
   import logging
   from fragmented_keys_django.cache_utils.decorators import tagged_cache as _tagged_cache

   logger = logging.getLogger("fragmented_keys.cache")

   def tagged_cache(**decorator_kwargs):
       """Drop-in replacement that logs cache hits and misses."""
       original_decorator = _tagged_cache(**decorator_kwargs)

       def wrapper(func):
           wrapped = original_decorator(func)

           from functools import wraps

           @wraps(func)
           def instrumented(*args, **kwargs):
               result = wrapped(*args, **kwargs)
               # The decorator returns early on hit (before calling func).
               # We can't distinguish hit/miss without reaching into internals,
               # so log at DEBUG level for key composition visibility.
               logger.debug(
                   "cache_access func=%s.%s",
                   func.__module__, func.__qualname__,
               )
               return result

           return instrumented

       return wrapper

For full hit/miss distinction, wrap at the backend level instead (see next
section).

**Signal handler logging:**

.. code-block:: python

   # myapp/apps.py — in AppConfig.ready()
   import logging
   from fragmented_keys_django import ModelTagManager

   logger = logging.getLogger("fragmented_keys.invalidation")

   _original_handler = ModelTagManager._on_model_change.__func__

   @classmethod
   def _logging_handler(cls, sender, instance, **kwargs):
       _original_handler(cls, sender, instance, **kwargs)
       tag_name = cls._registered_models.get(sender, sender.__name__)
       logger.info(
           "tag_incremented tag=%s pk=%s signal=%s",
           tag_name,
           instance.pk,
           "post_delete" if kwargs.get("signal") else "post_save",
       )

   ModelTagManager._on_model_change = _logging_handler


Metrics (StatsD / Prometheus)
-----------------------------

The backend's ``get``/``set``/``delete`` and ``*_with_tags`` methods are the
natural metric emission points.  Subclass the backend to add counters.

**StatsD example:**

.. code-block:: python

   # myapp/cache_backends.py
   from fragmented_keys_django.cache_backends.django_backend import (
       FragmentedKeysCacheBackend,
   )

   class InstrumentedFragmentedBackend(FragmentedKeysCacheBackend):
       """Adds StatsD metrics to every cache operation."""

       def __init__(self, params):
           super().__init__(params)
           import statsd
           self._stats = statsd.StatsClient(
               host=params.get("STATSD_HOST", "localhost"),
               port=int(params.get("STATSD_PORT", 8125)),
               prefix="fragmented_cache",
           )

       # ── Standard pass-through metrics ──

       def get(self, key, default=None, version=None):
           result = super().get(key, default, version)
           if result is default:
               self._stats.incr("get.miss")
           else:
               self._stats.incr("get.hit")
           return result

       def set(self, key, value, timeout=None, version=None):
           with self._stats.timer("set.time"):
               return super().set(key, value, timeout, version)

       def delete(self, key, version=None):
           self._stats.incr("delete")
           return super().delete(key, version)

       # ── Tag-aware metrics ──

       def _build_tagged_key(self, key, tags, group_id=""):
           """Key composition reads each tag's version from Redis."""
           n = len(tags)
           self._stats.incr("tag_version.read", n)
           self._stats.gauge("tags_per_key", n)
           with self._stats.timer("tag_version.read.time"):
               return super()._build_tagged_key(key, tags, group_id)

       def get_with_tags(self, key, tags, default=None, group_id=""):
           result = super().get_with_tags(key, tags, default, group_id)
           if result is default:
               self._stats.incr("get_with_tags.miss")
           else:
               self._stats.incr("get_with_tags.hit")
           return result

       def set_with_tags(self, key, value, tags, timeout=None, group_id=""):
           with self._stats.timer("set_with_tags.time"):
               return super().set_with_tags(key, value, tags, timeout, group_id)

       def invalidate_tags(self, tags):
           n = len(tags)
           self._stats.incr("tag_version.write", n)
           with self._stats.timer("tag_version.write.time"):
               count = super().invalidate_tags(tags)
           return count

Then point your settings at the subclass:

.. code-block:: python

   # settings.py
   CACHES = {
       "fragmented": {
           "BACKEND": "myapp.cache_backends.InstrumentedFragmentedBackend",
           "CACHE_NAME": "default",
           "PREFIX": "NOZ_FRAG",
           "STATSD_HOST": "statsd.internal",
       },
   }

**Prometheus example** — same pattern, swap the client:

.. code-block:: python

   from prometheus_client import Counter, Histogram

   CACHE_HITS = Counter("fragmented_cache_hits_total", "Cache hits", ["method"])
   CACHE_MISSES = Counter("fragmented_cache_misses_total", "Cache misses", ["method"])
   CACHE_LATENCY = Histogram("fragmented_cache_duration_seconds", "Op latency", ["method"])
   TAG_INVALIDATIONS = Counter("fragmented_tag_invalidations_total", "Tags incremented")
   TAGS_PER_KEY = Histogram(
       "fragmented_tags_per_key", "Number of tags per cache key",
       buckets=[1, 2, 3, 5, 8, 13],
   )
   TAG_VERSION_OPS = Counter(
       "fragmented_tag_version_ops_total",
       "Redis round-trips for tag version reads/writes",
       ["op"],  # "read" or "write"
   )
   TAG_VERSION_LATENCY = Histogram(
       "fragmented_tag_version_duration_seconds",
       "Latency of tag version Redis lookups",
       ["op"],
   )

   class PrometheusFragmentedBackend(FragmentedKeysCacheBackend):

       def _build_tagged_key(self, key, tags, group_id=""):
           n = len(tags)
           TAGS_PER_KEY.observe(n)
           TAG_VERSION_OPS.labels(op="read").inc(n)
           with TAG_VERSION_LATENCY.labels(op="read").time():
               return super()._build_tagged_key(key, tags, group_id)

       def get_with_tags(self, key, tags, default=None, group_id=""):
           with CACHE_LATENCY.labels(method="get_with_tags").time():
               result = super().get_with_tags(key, tags, default, group_id)
           if result is default:
               CACHE_MISSES.labels(method="get_with_tags").inc()
           else:
               CACHE_HITS.labels(method="get_with_tags").inc()
           return result

       def invalidate_tags(self, tags):
           n = len(tags)
           TAG_VERSION_OPS.labels(op="write").inc(n)
           with TAG_VERSION_LATENCY.labels(op="write").time():
               count = super().invalidate_tags(tags)
           TAG_INVALIDATIONS.inc(count)
           return count

**Key metrics to track:**

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Metric
     - Type
     - Why it matters
   * - ``get_with_tags.hit`` / ``miss``
     - Counter
     - Hit rate is the primary indicator of tag-cache effectiveness
   * - ``set_with_tags.time``
     - Histogram
     - Key composition queries Redis for each tag version — slow = too many tags
   * - ``invalidate_tags``
     - Counter
     - Spike = bulk writes or runaway signal handlers
   * - ``tag_version.read``
     - Counter
     - Redis GETs for tag version lookups during key composition — one per tag per cache operation
   * - ``tag_version.write``
     - Counter
     - Redis SETs for tag version increments during invalidation — one per tag
   * - ``tag_version.read.time`` / ``write.time``
     - Histogram
     - Latency of tag version Redis round-trips — directly proportional to tag count
   * - ``tags_per_key``
     - Histogram
     - Distribution of tag counts per key — drives Redis round-trip volume
   * - ``get.hit`` / ``miss``
     - Counter
     - Pass-through (non-tagged) cache health


Distributed tracing (OpenTelemetry)
-----------------------------------

If you run OpenTelemetry, add spans to the backend so cache operations appear
in your request traces.

.. code-block:: python

   # myapp/cache_backends.py
   from opentelemetry import trace
   from fragmented_keys_django.cache_backends.django_backend import (
       FragmentedKeysCacheBackend,
   )

   tracer = trace.get_tracer("fragmented_keys")

   class OTelFragmentedBackend(FragmentedKeysCacheBackend):

       def _build_tagged_key(self, key, tags, group_id=""):
           with tracer.start_as_current_span(
               "fragmented_cache.tag_version_read",
               attributes={
                   "cache.key": key,
                   "cache.tag_count": len(tags),
                   "cache.op": "read",
               },
           ):
               return super()._build_tagged_key(key, tags, group_id)

       def get_with_tags(self, key, tags, default=None, group_id=""):
           with tracer.start_as_current_span(
               "fragmented_cache.get_with_tags",
               attributes={
                   "cache.key": key,
                   "cache.tag_count": len(tags),
                   "cache.group_id": group_id,
               },
           ) as span:
               result = super().get_with_tags(key, tags, default, group_id)
               span.set_attribute("cache.hit", result is not default)
               return result

       def set_with_tags(self, key, value, tags, timeout=None, group_id=""):
           with tracer.start_as_current_span(
               "fragmented_cache.set_with_tags",
               attributes={
                   "cache.key": key,
                   "cache.tag_count": len(tags),
                   "cache.timeout": timeout or 0,
               },
           ):
               return super().set_with_tags(key, value, tags, timeout, group_id)

       def invalidate_tags(self, tags):
           with tracer.start_as_current_span(
               "fragmented_cache.tag_version_write",
               attributes={
                   "cache.tag_count": len(tags),
                   "cache.op": "write",
               },
           ) as span:
               count = super().invalidate_tags(tags)
               span.set_attribute("cache.invalidated_count", count)
               return count

The same ``BACKEND`` swap in settings applies.  All three approaches (StatsD,
Prometheus, OTel) can be combined in a single subclass if needed.


Django signals for custom hooks
-------------------------------

For side effects beyond metrics — Slack alerts on mass invalidation, audit
logs, cache warming — use Django signals to listen for model changes that
trigger tag increments.

.. code-block:: python

   # myapp/signals.py
   from django.db.models.signals import post_save, post_delete
   from django.dispatch import receiver
   from fragmented_keys_django import ModelTagManager

   @receiver(post_save)
   @receiver(post_delete)
   def on_any_registered_model_change(sender, instance, **kwargs):
       """Fire after ModelTagManager has already incremented the tag."""
       if not ModelTagManager.is_registered(sender):
           return

       tag_name = ModelTagManager.get_tag_name_for_model(sender)
       # Your custom logic here:
       #   - log to audit table
       #   - enqueue cache-warming task
       #   - send alert if invalidation rate exceeds threshold
       print(f"Cache tag {tag_name}:{instance.pk} was just incremented")

.. note::

   Django signal receivers fire in registration order.  ``ModelTagManager``
   connects its handlers in ``AppConfig.ready()``.  If you register your
   listener after that (e.g. in the same ``ready()`` method, after calling
   ``register_model()``), your receiver runs *after* the tag increment.


Annotating cache keys for debugging
------------------------------------

When debugging cache misses, it helps to know what composite key was generated
and which tag versions were embedded.  The backend's introspection methods
surface this.

.. code-block:: python

   from django.core.cache import caches

   frag = caches["fragmented"]

   # Check current tag version
   version = frag.get_tag_version("User", "42")
   print(f"User:42 is at version {version}")

   # Build the composite key without storing anything
   # (useful for checking what key would be generated)
   composite_key = frag._build_tagged_key("profile", [("User", "42")])
   print(f"Composite key: {composite_key}")

   # Check if the key exists in the underlying cache
   exists = frag.has_key(composite_key)
   print(f"Key exists: {exists}")

For deeper inspection, use the ``StandardTag`` and ``StandardKey`` objects
directly:

.. code-block:: python

   from fragmented_keys import StandardTag, StandardKey

   tag = StandardTag("User", "42", handler=frag._handler)
   print(f"Tag version key: {tag.get_tag_key()}")      # e.g. NOZ_FRAG:tag:User:42
   print(f"Tag version value: {tag.get_tag_version()}")  # e.g. 1710434567.123

   key = StandardKey("profile", [tag])
   print(f"Composed key: {key.get_key_str(hash=True)}")
   print(f"Unhashed key: {key.get_key_str(hash=False)}")  # human-readable


Recommended dashboard panels
-----------------------------

If you've instrumented with metrics, here are the panels worth watching:

1. **Hit rate** — ``hits / (hits + misses)`` for ``get_with_tags``.  Below 70%
   means your TTLs are too short or invalidation is too aggressive.

2. **Invalidation rate** — ``invalidate_tags`` per minute.  Spikes correlate
   with bulk writes or import jobs.  Sustained high rates suggest you may need
   coarser tags.

3. **Tag version read rate** — ``tag_version.read`` per second.  This is the
   actual Redis GET volume driven by key composition.  A single
   ``get_with_tags`` call with 4 tags = 4 Redis GETs for version lookups
   before the data GET.  Multiply by request rate to understand Redis load
   from tag resolution alone.

4. **Tag version I/O latency** (p95) — ``tag_version.read.time`` and
   ``tag_version.write.time``.  Directly proportional to tag count.  If this
   is slow, reduce tags per key or ensure ``get_multi`` batching is active
   (handled automatically by ``fragmented_keys``).

5. **Tags per key** (p50 / p95) — ``tags_per_key`` histogram.  Each tag adds
   a Redis ``GET`` to key composition.  If p95 is above 5, consider whether
   all those tags actually drive independent invalidation or whether some can
   be collapsed into a coarser tag.

6. **Tag version key count** — ``KEYS NOZ_FRAG:tag:*`` (run sparingly, not in
   production hot path).  Growing unboundedly means you're creating tags for
   ephemeral entities — consider adding TTLs to tag version keys.
