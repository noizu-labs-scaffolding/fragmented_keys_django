"""Global cache epoch — a single constant tag carried by every composite key.

The epoch is one immutable dimension prepended to every key this package
builds. Because it is a :class:`~fragmented_keys.tag.constant.ConstantTag`, it
never touches the cache backend and costs nothing at read time; but raising it
changes every composite key at once, which makes it a one-line global cache
bust.

**Why you would raise it.** Ordinarily you invalidate narrowly, by incrementing
the tag for the thing that changed. The epoch is for the cases where narrow
invalidation cannot express the problem:

- A key-derivation change. When the double-prefix defect was fixed (tags built
  outside the backend had been storing versions at ``:1::1:<tag>`` while the
  backend's own ``*_with_tags`` API used ``:1:<tag>``), the two namespaces
  merged. Entries written before the fix are still reachable under the merged
  naming but were computed under different assumptions. Raising the epoch as
  the fix rolls out makes every pre-fix entry unreachable instead.
- Promoting a build from stage to prod against a shared or restored cache.
- A payload schema change that keeps the same key shape.

**Position matters.** The epoch tag is always prepended, so it is the first
fragment of the raw key string. Tag order is significant, so every
implementation that wants matching keys must place it identically — see
``fragmented-keys-go``'s ``fragkeys.EpochTag`` and ``djangoredis.WithEpoch``.

**Setting it.** Either through the cache backend's ``EPOCH`` parameter::

    CACHES = {"default": {..., "PREFIX": "GNP", "EPOCH": 2.0}}

or explicitly::

    from fragmented_keys_django import configure_fragmented_keys
    configure_fragmented_keys(cache_name="default", prefix="GNP", epoch=2.0)

Raising it strands the previous generation of entries. They are not deleted;
they become unreachable and expire under their own TTL, which is the same
mechanism ordinary tag invalidation uses. Expect a cold cache immediately
after.
"""

from __future__ import annotations

from fragmented_keys.tag import ConstantTag

#: Tag name for the epoch dimension. Do not change it — it is part of the
#: cross-implementation key contract.
EPOCH_TAG_NAME = "epoch"

#: Instance for the epoch dimension. Constant; the epoch varies by *version*,
#: not by instance, so that raising it is a one-value change.
EPOCH_TAG_INSTANCE = "global"

#: Epoch applied when nothing has been configured.
DEFAULT_EPOCH = 1.0

_epoch: float = DEFAULT_EPOCH


def set_cache_epoch(epoch: float) -> None:
    """Set the process-wide cache epoch.

    Called for you by ``configure_fragmented_keys`` and by the cache backend's
    ``EPOCH`` parameter; call it directly only in tests.

    :param epoch: New epoch. Any change to this value invalidates every
        composite key built afterwards.
    """
    global _epoch
    _epoch = float(epoch)


def get_cache_epoch() -> float:
    """Return the process-wide cache epoch."""
    return _epoch


def epoch_tag(handler=None) -> ConstantTag:
    """Build the epoch tag for the current epoch.

    :param handler: Cache handler to attach. Irrelevant to behaviour — a
        constant tag never queries the backend — but keeping it consistent with
        its sibling tags avoids surprises if the tag is inspected.
    :returns: A :class:`ConstantTag` at the configured epoch version.
    """
    return ConstantTag(
        EPOCH_TAG_NAME,
        EPOCH_TAG_INSTANCE,
        version=_epoch,
        handler=handler,
    )


def is_epoch_tag(tag) -> bool:
    """Report whether *tag* is already an epoch tag.

    Used to keep :func:`with_epoch` idempotent, so a tag list that has passed
    through more than one entry point does not accumulate duplicates.
    """
    return (
        getattr(tag, "_tag", None) == EPOCH_TAG_NAME
        and getattr(tag, "_instance", None) == EPOCH_TAG_INSTANCE
    )


def with_epoch(tag_objs: list, handler=None) -> list:
    """Return *tag_objs* with the epoch tag prepended, idempotently.

    :param tag_objs: Tags for the key, in order.
    :param handler: Handler to attach to the epoch tag.
    :returns: A new list beginning with the epoch tag. If the list already
        begins with one, it is returned unchanged.
    """
    if tag_objs and is_epoch_tag(tag_objs[0]):
        return tag_objs
    return [epoch_tag(handler), *tag_objs]
