"""Optional model manager and queryset that fire tag invalidation on bulk ops.

Django's ``bulk_create``, ``bulk_update``, ``QuerySet.delete()``, and
``QuerySet.update()`` bypass ``post_save`` / ``post_delete`` signals. These
classes wrap those methods to call :meth:`ModelTagManager._fire_lifecycle`
after the operation completes.

Usage::

    from fragmented_keys_django import CacheAwareManager

    class OrganizationCategory(models.Model):
        objects = CacheAwareManager()
        # ...

After this, ``OrganizationCategory.objects.filter(org_id=42).delete()`` will
fire the ``on_delete`` lifecycle hook for each deleted instance.

.. note::

   ``CacheAwareQuerySet.delete()`` and ``.update()`` fetch all affected PKs
   before executing the operation (one extra SELECT). For very large querysets,
   consider calling :meth:`ModelTagManager.invalidate_bulk` manually instead.
"""

from __future__ import annotations

from typing import Any

from django.db import models


class _FakePKInstance:
    """Minimal instance-like object for lifecycle callbacks that only need pk."""

    def __init__(self, model: type, pk: Any) -> None:
        self.pk = pk
        self._meta = model._meta  # type: ignore[attr-defined]


class CacheAwareQuerySet(models.QuerySet):
    """QuerySet that fires tag invalidation on ``.delete()`` and ``.update()``."""

    def delete(self) -> tuple[int, dict[str, int]]:
        from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager

        pks = list(self.values_list("pk", flat=True))
        result = super().delete()
        for pk in pks:
            ModelTagManager._fire_lifecycle(
                "delete", self.model, _FakePKInstance(self.model, pk)
            )
        return result

    def update(self, **kwargs: Any) -> int:
        from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager

        pks = list(self.values_list("pk", flat=True))
        result = super().update(**kwargs)
        for pk in pks:
            ModelTagManager._fire_lifecycle(
                "update",
                self.model,
                _FakePKInstance(self.model, pk),
                update_fields=list(kwargs.keys()),
            )
        return result


class CacheAwareManager(models.Manager):
    """Manager that fires tag invalidation on bulk operations.

    Provides a :class:`CacheAwareQuerySet` as the default queryset, so
    ``.filter().delete()`` and ``.filter().update()`` automatically fire
    lifecycle hooks.  Also wraps ``bulk_create`` and ``bulk_update``.
    """

    def get_queryset(self) -> CacheAwareQuerySet:
        return CacheAwareQuerySet(self.model, using=self._db)

    def bulk_create(
        self, objs: list, batch_size: int | None = None, **kwargs: Any
    ) -> list:
        from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager

        result = super().bulk_create(objs, batch_size=batch_size, **kwargs)
        for obj in result:
            if obj.pk is not None:
                ModelTagManager._fire_lifecycle("create", type(obj), obj)
        return result

    def bulk_update(
        self, objs: list, fields: list[str], batch_size: int | None = None, **kwargs: Any
    ) -> int:
        from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager

        result = super().bulk_update(objs, fields, batch_size=batch_size, **kwargs)
        for obj in objs:
            if obj.pk is not None:
                ModelTagManager._fire_lifecycle(
                    "update", type(obj), obj, update_fields=fields
                )
        return result
