"""Tests for tag factory utilities."""

import pytest

from fragmented_keys_django.cache_utils.tags import (
    model_tag,
    list_tag,
    aggregate_tag,
    custom_tag,
    parse_tag_template,
    resolve_tag_instance,
    resolve_param_value,
    build_composite_key,
)


class TestTagFactories:
    """Tests for tag factory functions."""

    def test_model_tag(self):
        """Test model_tag creates StandardTag correctly."""
        tag = model_tag("User", "42")

        assert tag is not None
        # Tag should have correct instance value
        assert tag._instance == "42"

    def test_model_tag_with_int_instance(self):
        """Test model_tag with integer instance."""
        tag = model_tag("User", 42)

        assert tag._instance == "42"

    def test_list_tag(self):
        """Test list_tag creates StandardTag correctly."""
        tag = list_tag("Donations", "user_123")

        assert tag is not None
        assert tag._instance == "user_123"

    def test_aggregate_tag(self):
        """Test aggregate_tag creates StandardTag correctly."""
        tag = aggregate_tag("DashboardStats", "daily_2024")

        assert tag is not None
        assert tag._instance == "daily_2024"

    def test_custom_tag(self):
        """Test custom_tag creates StandardTag correctly."""
        tag = custom_tag("Weather", "NYC_20240115")

        assert tag is not None
        assert tag._instance == "NYC_20240115"


class TestParseTagTemplate:
    """Tests for parse_tag_template function."""

    def test_parse_simple_template(self):
        """Test parsing a simple tag template."""
        tag_name, pattern = parse_tag_template("User:{user_id}")

        assert tag_name == "User"
        assert pattern == "{user_id}"

    def test_parse_template_no_placeholder(self):
        """Test parsing template without placeholder."""
        tag_name, pattern = parse_tag_template("Dashboard")

        assert tag_name == "Dashboard"
        assert pattern == ""

    def test_parse_template_with_extra_text(self):
        """Test parsing template with extra text."""
        tag_name, pattern = parse_tag_template("Campaign_{id}_Stats")

        assert "Campaign_" in tag_name
        assert pattern.startswith("{")

    def test_parse_template_multiple_placeholders(self):
        """Test parsing template with multiple placeholders."""
        tag_name, pattern = parse_tag_template("User:{user_id}:Campaign:{campaign_id}")

        assert "User" in tag_name
        assert "{user_id}" in pattern


class TestResolveTagInstance:
    """Tests for resolve_tag_instance function."""

    def test_resolve_from_kwargs(self):
        """Test resolving instance from kwargs."""
        template = "User:{user_id}"

        def test_func(user_id):
            pass

        result = resolve_tag_instance(template, (), {"user_id": 42}, test_func)
        assert result == "42"

    def test_resolve_from_args(self):
        """Test resolving instance from positional args."""
        template = "Campaign:{campaign_id}"

        def test_func(campaign_id):
            pass

        result = resolve_tag_instance(template, (100,), {}, test_func)
        assert result == "100"

    def test_resolve_no_placeholder(self):
        """Test resolving when no placeholder exists."""
        template = "Global"

        def test_func():
            pass

        result = resolve_tag_instance(template, (), {}, test_func)
        assert result == ""

    def test_resolve_missing_param(self):
        """Test resolving when parameter doesn't exist."""
        template = "User:{missing}"

        def test_func(user_id):
            pass

        result = resolve_tag_instance(template, (42,), {}, test_func)
        assert result == ""


class TestResolveParamValue:
    """Tests for resolve_param_value function."""

    def test_resolve_from_kwargs(self):
        """Test resolving parameter from kwargs."""
        def test_func(param1, param2):
            pass

        result = resolve_param_value("param1", (), {"param1": "value1"}, test_func)
        assert result == "value1"

    def test_resolve_from_positional_args(self):
        """Test resolving parameter from positional args."""
        def test_func(a, b, c):
            pass

        result = resolve_param_value("b", ("A", "B", "C"), {}, test_func)
        assert result == "B"

    def test_resolve_self_in_method(self):
        """Test resolving self parameter."""
        class TestClass:
            def method(self, param):
                pass

        instance = TestClass()
        result = resolve_param_value("self", (instance,), {}, TestClass.method)
        assert result is instance

    def test_resolve_param_not_found_raises_keyerror(self):
        """Test that missing parameter raises KeyError."""
        def test_func(a):
            pass

        with pytest.raises(KeyError):
            resolve_param_value("nonexistent", (), {}, test_func)

    def test_resolve_kwarg_overrides_positional(self):
        """Test that kwargs override positional args."""
        def test_func(a, b):
            pass

        result = resolve_param_value(
            "a",
            ("positional_a", "positional_b"),
            {"a": "keyword_a"},
            test_func,
        )
        # Should return keyword value
        assert result == "keyword_a"


class TestBuildCompositeKey:
    """Tests for build_composite_key function."""

    def test_build_no_tags_no_params(self):
        """Test building composite key with no tags or params."""
        tag_objs, key_name = build_composite_key("TestKey")

        assert tag_objs == []
        assert key_name == "TestKey"

    def test_build_with_tags_only(self):
        """Test building composite key with tags only."""
        tags = [("User", "42"), ("Campaign", "100")]

        tag_objs, key_name = build_composite_key("MyFunction", tags=tags)

        assert len(tag_objs) == 2
        assert key_name == "MyFunction"

    def test_build_with_params_only(self):
        """Test building composite key with varying params only."""
        params = [("user_id", "42"), ("filter", "active")]

        tag_objs, key_name = build_composite_key("View", vary_params=params)

        assert tag_objs == []
        assert "user_id_42" in key_name
        assert "filter_active" in key_name

    def test_build_with_tags_and_params(self):
        """Test building composite key with both tags and params."""
        tags = [("User", "42")]
        params = [("sort", "asc")]

        tag_objs, key_name = build_composite_key("List", tags=tags, vary_params=params)

        assert len(tag_objs) == 1
        assert "sort_asc" in key_name

    def test_build_tags_contain_correct_instances(self):
        """Test that built tags have correct instance values."""
        tags = [("Model", "123")]

        tag_objs, _ = build_composite_key("Test", tags=tags)

        assert len(tag_objs) == 1
        assert tag_objs[0]._instance == "123"

    def test_build_empty_tags_list(self):
        """Test building with empty tags list."""
        tag_objs, key_name = build_composite_key("Key", tags=[])

        assert tag_objs == []

    def test_build_empty_params_list(self):
        """Test building with empty params list."""
        tag_objs, key_name = build_composite_key("Key", vary_params=[])

        assert tag_objs == []
        assert key_name == "Key"