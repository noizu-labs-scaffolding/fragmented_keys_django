"""Tests for ModelTagManager."""

from unittest.mock import MagicMock, patch

import pytest

from fragmented_keys_django.cache_utils.model_helpers import ModelTagManager


# --- Fixtures ---

@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure ModelTagManager is clean before/after each test."""
    ModelTagManager.clear_all()
    yield
    ModelTagManager.clear_all()


@pytest.fixture
def mock_model_class():
    model = MagicMock()
    model.__name__ = "MockModel"
    return model


@pytest.fixture
def mock_model_instance():
    instance = MagicMock()
    instance.pk = 42
    return instance


# --- Basic Registration ---

class TestRegistration:
    def test_register_model(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class)

        assert ModelTagManager.is_registered(mock_model_class)
        assert ModelTagManager.get_tag_name_for_model(mock_model_class) == "MockModel"

    def test_register_model_custom_name(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class, tag_name="custom")

        assert ModelTagManager.get_tag_name_for_model(mock_model_class) == "custom"

    def test_register_model_no_auto_connect(self, mock_model_class):
        with patch.object(ModelTagManager, "connect_signals") as mock_connect:
            ModelTagManager.register_model(mock_model_class, auto_connect=False)
            mock_connect.assert_not_called()

    def test_unregister_model(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        assert ModelTagManager.is_registered(mock_model_class)

        ModelTagManager.unregister_model(mock_model_class)
        assert not ModelTagManager.is_registered(mock_model_class)

    def test_get_registered_models(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        registered = ModelTagManager.get_registered_models()

        assert mock_model_class in registered
        assert registered[mock_model_class] == "MockModel"

    def test_get_registered_config(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class, tag_name="test")
        config = ModelTagManager.get_registered_config(mock_model_class)

        assert config["tag_name"] == "test"
        assert config["on_create"] is None
        assert config["on_update"] is None
        assert config["on_delete"] is None

    def test_clear_all(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        assert len(ModelTagManager.get_registered_models()) > 0

        ModelTagManager.clear_all()
        assert len(ModelTagManager.get_registered_models()) == 0


# --- Signal Handlers (default behavior) ---

class TestDefaultSignalHandlers:
    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_save_create(self, mock_tag_cls, mock_model_class, mock_model_instance):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=True,
            update_fields=None,
        )

        # Per-instance tag + global * tag
        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("MockModel", "42")
        mock_tag_cls.assert_any_call("MockModel", "*")
        assert mock_tag.increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_save_update(self, mock_tag_cls, mock_model_class, mock_model_instance):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=False,
            update_fields={"name"},
        )

        # Per-instance tag + global * tag
        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("MockModel", "42")
        mock_tag_cls.assert_any_call("MockModel", "*")
        assert mock_tag.increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_delete(self, mock_tag_cls, mock_model_class, mock_model_instance):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_delete(
            sender=mock_model_class,
            instance=mock_model_instance,
        )

        # Per-instance tag + global * tag
        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("MockModel", "42")
        mock_tag_cls.assert_any_call("MockModel", "*")
        assert mock_tag.increment.call_count == 2

    def test_on_model_save_none_pk(self, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        instance = MagicMock()
        instance.pk = None

        ModelTagManager._on_model_save(
            sender=mock_model_class, instance=instance, created=True
        )

    def test_on_model_save_unregistered(self):
        mock_model = MagicMock()
        ModelTagManager._on_model_save(
            sender=mock_model, instance=MagicMock(), created=True
        )

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_model_save_exception_silenced(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag.increment.side_effect = ConnectionError("Redis down")
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class, instance=mock_model_instance, created=True
        )


# --- Lifecycle Hooks ---

class TestLifecycleHooks:
    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_create_hook(self, mock_tag_cls, mock_model_class, mock_model_instance):
        def on_create(sender, instance):
            return [
                ("mock", str(instance.pk)),
                ("mock", "scope:all"),
            ]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_create=on_create
        )
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=True,
        )

        # 2 explicit tags + 1 global * tag (deduplicated by tag_name)
        assert mock_tag_cls.call_count == 3
        mock_tag_cls.assert_any_call("mock", "42")
        mock_tag_cls.assert_any_call("mock", "scope:all")
        mock_tag_cls.assert_any_call("mock", "*")
        assert mock_tag.increment.call_count == 3

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_update_hook_receives_update_fields(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        received = {}

        def on_update(sender, instance, update_fields):
            received["update_fields"] = update_fields
            return [("mock", str(instance.pk))]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_update=on_update
        )
        mock_tag_cls.return_value = MagicMock()

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=False,
            update_fields={"name", "email"},
        )

        assert received["update_fields"] == {"name", "email"}

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_on_delete_hook(self, mock_tag_cls, mock_model_class, mock_model_instance):
        def on_delete(sender, instance):
            return [
                ("mock", str(instance.pk)),
                ("mock", "scope:parent"),
            ]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_delete=on_delete
        )
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_delete(
            sender=mock_model_class,
            instance=mock_model_instance,
        )

        # 2 explicit tags + 1 global * tag
        assert mock_tag_cls.call_count == 3
        mock_tag_cls.assert_any_call("mock", "*")
        assert mock_tag.increment.call_count == 3

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_create_hook_only_fires_on_create(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """on_create hook should not fire for updates."""
        create_called = []

        def on_create(sender, instance):
            create_called.append(True)
            return [("mock", str(instance.pk))]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_create=on_create
        )
        mock_tag_cls.return_value = MagicMock()

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=False,
        )

        assert len(create_called) == 0

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_update_fallback_when_no_hook(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """Without on_update hook, update falls back to default."""
        ModelTagManager.register_model(
            mock_model_class, tag_name="mock",
            on_create=lambda s, i: [("mock", "custom")],
        )
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=False,
        )

        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("mock", "42")
        mock_tag_cls.assert_any_call("mock", "*")


# --- Manual Invalidation ---

class TestManualInvalidation:
    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_by_class(self, mock_tag_cls, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)

        assert result is True
        # instance tag + global * tag
        assert mock_tag.increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_by_name(self, mock_tag_cls, mock_model_class):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag("MockModel", 42)

        assert result is True
        # instance tag + global * tag
        assert mock_tag.increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_by_tag_name(self, mock_tag_cls, mock_model_class):
        """Can resolve by tag_name string, not just model __name__."""
        ModelTagManager.register_model(mock_model_class, tag_name="custom_tag")
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        result = ModelTagManager.invalidate_model_tag("custom_tag", 42)

        assert result is True

    def test_invalidate_model_tag_not_registered(self, mock_model_class):
        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)
        assert result is False

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_model_tag_exception_returns_false(
        self, mock_tag_cls, mock_model_class
    ):
        ModelTagManager.register_model(mock_model_class)
        mock_tag = MagicMock()
        mock_tag.increment.side_effect = ConnectionError("Redis down")
        mock_tag_cls.return_value = mock_tag

        # _increment_tags swallows exceptions internally, so the outer
        # try/except in invalidate_model_tag sees no exception and returns True.
        result = ModelTagManager.invalidate_model_tag(mock_model_class, 42)
        assert result is True

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_scope(self, mock_tag_cls):
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        result = ModelTagManager.invalidate_scope("review", "org:42")

        assert result is True
        # scope tag + global * tag via _increment_tags
        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("review", "org:42")
        mock_tag_cls.assert_any_call("review", "*")
        assert mock_tag.increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_bulk_with_pks_and_scopes(self, mock_tag_cls, mock_model_class):
        ModelTagManager.register_model(mock_model_class, tag_name="mock")
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        count = ModelTagManager.invalidate_bulk(
            mock_model_class, pks=[1, 2], scopes=["org:42"]
        )

        assert count == 3
        # 3 explicit tags + 1 global * tag (deduplicated per tag_name)
        assert mock_tag.increment.call_count == 4

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_invalidate_bulk_by_tag_name(self, mock_tag_cls):
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        # Register a mock model so tag name resolves
        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        ModelTagManager.register_model(mock_model, tag_name="test")

        count = ModelTagManager.invalidate_bulk("test", scopes=["scope:1"])
        assert count == 1


# --- _fire_lifecycle ---

class TestFireLifecycle:
    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_fire_lifecycle_create(self, mock_tag_cls, mock_model_class, mock_model_instance):
        def on_create(sender, instance):
            return [("mock", str(instance.pk)), ("mock", "scope:all")]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_create=on_create
        )
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._fire_lifecycle("create", mock_model_class, mock_model_instance)

        # 2 explicit tags + 1 global * tag
        assert mock_tag.increment.call_count == 3

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_fire_lifecycle_update_with_fields(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        received = {}

        def on_update(sender, instance, update_fields):
            received["fields"] = update_fields
            return [("mock", str(instance.pk))]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_update=on_update
        )
        mock_tag_cls.return_value = MagicMock()

        ModelTagManager._fire_lifecycle(
            "update", mock_model_class, mock_model_instance,
            update_fields=["name"]
        )

        assert received["fields"] == ["name"]

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_fire_lifecycle_default_when_no_hook(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        ModelTagManager.register_model(mock_model_class, tag_name="mock")
        mock_tag = MagicMock()
        mock_tag_cls.return_value = mock_tag

        ModelTagManager._fire_lifecycle("delete", mock_model_class, mock_model_instance)

        assert mock_tag_cls.call_count == 2
        mock_tag_cls.assert_any_call("mock", "42")
        mock_tag_cls.assert_any_call("mock", "*")
        assert mock_tag.increment.call_count == 2

    def test_fire_lifecycle_unregistered_is_noop(self):
        mock_model = MagicMock()
        mock_instance = MagicMock()
        mock_instance.pk = 1

        ModelTagManager._fire_lifecycle("create", mock_model, mock_instance)


# --- Signal Connection ---

class TestSignalConnection:
    def test_connect_signals(self, mock_model_class):
        from django.db.models.signals import post_save, post_delete

        with patch.object(post_save, "connect") as mock_save, \
             patch.object(post_delete, "connect") as mock_delete:
            ModelTagManager.connect_signals(mock_model_class)

            mock_save.assert_called_once()
            mock_delete.assert_called_once()

    def test_disconnect_signals(self, mock_model_class):
        from django.db.models.signals import post_save, post_delete

        with patch.object(post_save, "disconnect") as mock_save_disc, \
             patch.object(post_delete, "disconnect") as mock_delete_disc:
            ModelTagManager.register_model(mock_model_class)
            ModelTagManager.disconnect_signals(mock_model_class)

            mock_save_disc.assert_called_once()
            mock_delete_disc.assert_called_once()

    @patch("django.apps.apps.get_model")
    def test_get_tag_name_via_app_label(self, mock_get_model, mock_model_class):
        ModelTagManager.register_model(mock_model_class)

        other_ref = MagicMock()
        mock_get_model.return_value = mock_model_class

        result = ModelTagManager.get_tag_name_for_model(other_ref)
        assert result == "MockModel"

    @patch("django.apps.apps.get_model")
    def test_get_tag_name_app_lookup_fails(self, mock_get_model):
        mock_get_model.side_effect = LookupError("No such model")

        unknown = MagicMock()
        result = ModelTagManager.get_tag_name_for_model(unknown)
        assert result is None


# --- Global * Tag Bump ---

class TestGlobalStarTagBump:
    """Tests for the temporary global * tag bump in _increment_tags.

    When _on_model_change fires (save/delete), both the per-instance tag
    AND the global * tag for that tag_name must be incremented so that
    1-tuple cache keys (resolving to StandardTag(name, "*")) are invalidated.
    """

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_save_bumps_both_instance_and_global(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """When User(pk=42) is saved, both StandardTag("user", "42")
        and StandardTag("user", "*") get incremented."""
        ModelTagManager.register_model(mock_model_class, tag_name="user")

        # Track calls with distinct mock objects per (tag_name, instance_id)
        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=True,
        )

        # Both tags must exist
        assert ("user", "42") in tags_created, "Per-instance tag not created"
        assert ("user", "*") in tags_created, "Global * tag not created"

        # Both must have been incremented
        tags_created[("user", "42")].increment.assert_called_once()
        tags_created[("user", "*")].increment.assert_called_once()

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_per_instance_tags_independent(
        self, mock_tag_cls, mock_model_class
    ):
        """Bumping user 42 does not affect user 43's per-instance tag."""
        ModelTagManager.register_model(mock_model_class, tag_name="user")

        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        instance_42 = MagicMock()
        instance_42.pk = 42

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=instance_42,
            created=True,
        )

        # user:42 was bumped, user:43 was never touched
        assert ("user", "42") in tags_created
        assert ("user", "43") not in tags_created

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_global_star_shared_across_instances(
        self, mock_tag_cls, mock_model_class
    ):
        """The global * tag is the same for all instances of a tag_name."""
        ModelTagManager.register_model(mock_model_class, tag_name="user")

        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        instance_42 = MagicMock()
        instance_42.pk = 42
        instance_43 = MagicMock()
        instance_43.pk = 43

        ModelTagManager._on_model_save(
            sender=mock_model_class, instance=instance_42, created=True,
        )
        ModelTagManager._on_model_save(
            sender=mock_model_class, instance=instance_43, created=False,
        )

        # Global * tag was bumped twice (once per save), using the same key
        assert ("user", "*") in tags_created
        assert tags_created[("user", "*")].increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_global_star_not_double_bumped_when_explicit(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """If a lifecycle hook already returns ("tag", "*"), it should not
        be bumped a second time by the automatic global * logic."""

        def on_create(sender, instance):
            return [
                ("mock", str(instance.pk)),
                ("mock", "*"),  # hook explicitly includes *
            ]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_create=on_create
        )

        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=True,
        )

        # * was explicitly in the list, so it gets bumped once (from the
        # explicit entry). The automatic global * logic skips it for "mock"
        # because the first entry ("42") triggers the auto-bump, but
        # the explicit "*" should only be incremented once total.
        # Actually: "42" triggers auto-bump of *, then "*" is in the list
        # but since instance_id == "*" the auto-bump skips it.
        # So * gets incremented twice: once from auto-bump of "42", once
        # from the explicit ("mock", "*") entry.
        assert tags_created[("mock", "*")].increment.call_count == 2

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_global_star_deduplicated_per_tag_name(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """When a lifecycle hook returns multiple tags with the same tag_name,
        the global * bump only happens once per unique tag_name."""

        def on_create(sender, instance):
            return [
                ("mock", str(instance.pk)),
                ("mock", "scope:org:1"),
                ("mock", "scope:org:2"),
            ]

        ModelTagManager.register_model(
            mock_model_class, tag_name="mock", on_create=on_create
        )

        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        ModelTagManager._on_model_save(
            sender=mock_model_class,
            instance=mock_model_instance,
            created=True,
        )

        # 3 explicit tags + 1 global * = 4 total StandardTag constructions
        assert len(tags_created) == 4
        assert tags_created[("mock", "*")].increment.call_count == 1

    @patch("fragmented_keys_django.cache_utils.model_helpers.StandardTag")
    def test_delete_also_bumps_global_star(
        self, mock_tag_cls, mock_model_class, mock_model_instance
    ):
        """post_delete also bumps the global * tag."""
        ModelTagManager.register_model(mock_model_class, tag_name="user")

        tags_created = {}

        def make_tag(name, instance_id):
            key = (name, instance_id)
            if key not in tags_created:
                tags_created[key] = MagicMock(name=f"Tag({name},{instance_id})")
            return tags_created[key]

        mock_tag_cls.side_effect = make_tag

        ModelTagManager._on_model_delete(
            sender=mock_model_class,
            instance=mock_model_instance,
        )

        assert ("user", "42") in tags_created
        assert ("user", "*") in tags_created
        tags_created[("user", "42")].increment.assert_called_once()
        tags_created[("user", "*")].increment.assert_called_once()
