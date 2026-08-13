"""Tests for CacheAwareManager and CacheAwareQuerySet."""

from unittest.mock import MagicMock, patch

import pytest

from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager


@pytest.fixture(autouse=True)
def clean_registry():
    ModelTagManager.clear_all()
    yield
    ModelTagManager.clear_all()


class TestCacheAwareManager:
    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_bulk_create_fires_lifecycle(self, mock_tag_cls):
        from fragmented_keys_django.cache_utils.bulk import CacheAwareManager

        mock_model = MagicMock()
        mock_model.__name__ = "Item"
        ModelTagManager.register_model(mock_model, tag_name="item")

        obj1 = MagicMock(spec=["pk"])
        obj1.pk = 1
        obj2 = MagicMock(spec=["pk"])
        obj2.pk = 2

        mock_tag_cls.return_value = MagicMock()

        with patch.object(ModelTagManager, "_fire_lifecycle") as mock_fire:
            manager = CacheAwareManager()
            manager.model = mock_model

            with patch.object(
                CacheAwareManager.__bases__[0], "bulk_create", return_value=[obj1, obj2]
            ):
                manager.bulk_create([obj1, obj2])

            assert mock_fire.call_count == 2


class TestFakePKInstance:
    def test_has_pk(self):
        from fragmented_keys_django.cache_utils.bulk import _FakePKInstance

        mock_model = MagicMock()
        fake = _FakePKInstance(mock_model, 42)
        assert fake.pk == 42
