from __future__ import annotations

import json

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime import tool_registry as tool_registry_module
from worker.runtime.tool_registry import (
    BUILTIN_AGENTIC_TOOL_NAMES,
    ToolArgumentDescriptor,
    ToolDescriptor,
    ToolRegistry,
    ToolRegistryError,
    built_in_tool_config,
    built_in_tool_registry,
)


def test_built_in_agentic_tool_registry_exports_stable_contracts() -> None:
    registry = built_in_tool_registry()

    assert registry.names() == BUILTIN_AGENTIC_TOOL_NAMES
    assert registry.metrics().tool_count == 6
    assert registry.metrics().required_argument_count == 7
    assert registry.metrics().schema_bytes > 0

    schemas = registry.as_openai_tools()
    assert [schema["function"]["name"] for schema in schemas] == list(BUILTIN_AGENTIC_TOOL_NAMES)
    assert {schema["type"] for schema in schemas} == {"function"}
    assert schemas[0]["x-melix-tool-kind"] == "vision.image_crop"
    assert schemas[0]["x-melix-observation-kind"] == "image_region"


def test_built_in_tool_registry_reuses_singleton_snapshot() -> None:
    registry = built_in_tool_registry()

    assert built_in_tool_registry() is registry
    assert registry.names() == BUILTIN_AGENTIC_TOOL_NAMES


def test_tool_registry_openai_tools_reuses_cached_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    expected_tools = registry.as_openai_tools()

    def fail_as_openai_tool(self: ToolDescriptor) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("as_openai_tools() should reuse cached templates")

    monkeypatch.setattr(ToolDescriptor, "as_openai_tool", fail_as_openai_tool)

    tools = registry.as_openai_tools()

    assert tools == expected_tools
    assert tools is not expected_tools
    assert tools[0] is not expected_tools[0]
    tools[0]["function"]["parameters"]["properties"]["media_ref"]["description"] = "mutated"
    tools[0]["function"]["parameters"]["required"].append("mutated")
    assert registry.as_openai_tools()[0]["function"]["parameters"]["properties"]["media_ref"][
        "description"
    ] == "Identifier or URI for the source image."
    assert registry.as_openai_tools()[0]["function"]["parameters"]["required"] == [
        "media_ref",
        "region",
    ]


def test_built_in_tool_config_returns_isolated_template_copies() -> None:
    first_config = built_in_tool_config()
    first_config.tools.pop()
    first_config.schema_version = "mutated"

    second_config = built_in_tool_config()

    assert len(second_config.tools) == len(BUILTIN_AGENTIC_TOOL_NAMES)
    assert second_config.schema_version == tool_registry_module.TOOL_REGISTRY_SCHEMA_VERSION


def test_built_in_tool_config_selection_returns_isolated_template_copies() -> None:
    first_config = built_in_tool_config(("image_crop", "local_compute"))
    first_config.tools.pop()
    first_config.schema_version = "mutated"

    second_config = built_in_tool_config(("image_crop", "local_compute"))

    assert [tool.name for tool in second_config.tools] == ["image_crop", "local_compute"]
    assert second_config.schema_version == tool_registry_module.TOOL_REGISTRY_SCHEMA_VERSION


def test_built_in_tool_schemas_are_object_contracts_with_required_arguments() -> None:
    registry = built_in_tool_registry()

    for tool in registry.tools:
        parsed = json.loads(tool.json_schema())
        assert parsed["type"] == "object"
        assert parsed["additionalProperties"] is False
        assert parsed["required"]
        assert set(parsed["required"]).issubset(parsed["properties"])
        assert "x-melix-tool-kind" not in parsed
        assert "x-melix-observation-kind" not in parsed


def test_tool_registry_metrics_reuses_cached_schema_byte_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = built_in_tool_registry()
    expected_schema_bytes = sum(len(tool.json_schema().encode("utf-8")) for tool in registry.tools)

    def fail_json_schema(self: ToolDescriptor) -> str:
        raise AssertionError("metrics() should not re-encode cached JSON schemas")

    monkeypatch.setattr(ToolDescriptor, "json_schema", fail_json_schema)

    with pytest.raises(AssertionError, match=r"metrics\(\) should not re-encode"):
        registry.tools[0].json_schema()
    assert registry.metrics().schema_bytes == expected_schema_bytes


def test_tool_registry_metrics_reuses_registry_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = built_in_tool_registry()
    expected_metrics = registry.metrics()

    def fail_schema_byte_count(self: ToolDescriptor) -> int:
        raise AssertionError("metrics() should reuse the registry metrics snapshot")

    monkeypatch.setattr(ToolDescriptor, "schema_byte_count", fail_schema_byte_count)

    with pytest.raises(AssertionError, match=r"metrics\(\) should reuse"):
        registry.tools[0].schema_byte_count()
    assert registry.metrics() is expected_metrics
    assert registry.metrics().schema_bytes == expected_metrics.schema_bytes


def test_tool_registry_metrics_snapshot_updates_for_selected_registry() -> None:
    registry = built_in_tool_registry()

    selected = registry.select(["visit", "image_crop", "visit"])

    assert selected.metrics().tool_count == 2
    assert selected.metrics().schema_bytes == sum(
        tool.schema_byte_count() for tool in selected.tools
    )


def test_tool_registry_names_reuses_registry_snapshot() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    expected_names = registry.names()
    object.__setattr__(registry, "_tools", ())

    assert registry.names() is expected_names
    assert registry.names() == BUILTIN_AGENTIC_TOOL_NAMES


def test_tool_registry_descriptors_use_slotted_snapshots() -> None:
    registry = built_in_tool_registry()

    assert not hasattr(registry.metrics(), "__dict__")
    assert not hasattr(registry.tools[0], "__dict__")
    assert not hasattr(registry.tools[0].arguments[0], "__dict__")


def test_tool_descriptor_required_arguments_reuses_cached_snapshot() -> None:
    tool = built_in_tool_registry().tools[0]
    expected_required_arguments = tool.required_arguments
    object.__setattr__(tool, "arguments", ())

    assert tool.required_arguments is expected_required_arguments
    assert tool.required_arguments == ("media_ref", "region")
    assert tool.schema_payload()["required"] == ["media_ref", "region"]


def test_tool_descriptor_schema_payload_reuses_cached_argument_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = built_in_tool_registry().tools[0]

    def fail_json_schema(self: ToolArgumentDescriptor) -> dict[str, str]:  # pragma: no cover
        raise AssertionError("schema_payload() should reuse cached argument schemas")

    monkeypatch.setattr(ToolArgumentDescriptor, "json_schema", fail_json_schema)

    payload = tool.schema_payload()

    assert payload["properties"]["media_ref"] == {
        "type": "string",
        "description": "Identifier or URI for the source image.",
    }


def test_tool_descriptor_schema_payload_returns_isolated_mutable_payloads() -> None:
    tool = built_in_tool_registry().tools[0]

    first_payload = tool.schema_payload()
    first_payload["properties"]["media_ref"]["description"] = "mutated"
    first_payload["required"].append("mutated")

    second_payload = tool.schema_payload()

    assert second_payload["properties"]["media_ref"]["description"] == (
        "Identifier or URI for the source image."
    )
    assert second_payload["required"] == ["media_ref", "region"]


def test_tool_registry_rejects_duplicate_tool_names() -> None:
    registry = built_in_tool_registry()

    with pytest.raises(ToolRegistryError, match="Duplicate tool registry entry"):
        ToolRegistry([registry.tools[0], registry.tools[0]])


def test_tool_registry_rejects_unknown_requested_names() -> None:
    registry = built_in_tool_registry()

    with pytest.raises(ToolRegistryError, match="Unknown tool registry entry requested"):
        registry.select(["image_crop", "missing_tool"])


def test_tool_registry_selects_tools_in_requested_order() -> None:
    registry = built_in_tool_registry()

    selected = registry.select(["visit", "image_crop", "visit"])

    assert selected.names() == ("visit", "image_crop")


def test_tool_registry_select_trims_blanks_and_deduplicates_in_one_pass() -> None:
    registry = built_in_tool_registry()

    selected = registry.select([" visit ", "", "image_crop", "visit", "  "])

    assert selected.names() == ("visit", "image_crop")


def test_tool_registry_select_reuses_cached_name_index() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    object.__setattr__(registry, "_tools", ())

    selected = registry.select(["visit", "image_crop", "visit"])

    assert selected.names() == ("visit", "image_crop")


def test_tool_registry_select_looks_up_each_selected_name_once() -> None:
    class CountingIndex(dict[str, ToolDescriptor]):
        def __init__(self, values: dict[str, ToolDescriptor]) -> None:
            super().__init__(values)
            self.get_calls = 0
            self.contains_calls = 0

        def get(self, key: str, default: object = None) -> ToolDescriptor | object:
            self.get_calls += 1
            return super().get(key, default)

        def __contains__(self, key: object) -> bool:
            self.contains_calls += 1
            return super().__contains__(key)

    registry = ToolRegistry(built_in_tool_registry().tools)
    index = CountingIndex(registry._tool_by_name)
    assert "visit" in index
    index.contains_calls = 0
    object.__setattr__(registry, "_tool_by_name", index)

    selected = registry.select(["visit", "image_crop", "visit"])

    assert selected.names() == ("visit", "image_crop")
    assert index.get_calls == 2
    assert index.contains_calls == 0


def test_tool_registry_select_reuses_cached_selected_registry() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    selected = registry.select([" visit ", "image_crop", "visit"])

    assert registry.select(["visit", "image_crop"]) is selected
    assert selected.names() == ("visit", "image_crop")


def test_tool_registry_select_tuple_cache_hit_skips_name_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    selected = registry.select(("visit", "image_crop"))

    monkeypatch.setattr(registry, "_tool_by_name", {})

    assert registry.select(("visit", "image_crop")) is selected
    with pytest.raises(ToolRegistryError, match="Unknown tool registry entry requested"):
        registry.select(["image_crop", "visit"])


def test_tool_registry_select_caches_raw_tuple_alias_after_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    selected = registry.select((" visit ", "image_crop", "visit", ""))

    monkeypatch.setattr(registry, "_tool_by_name", {})

    assert selected.names() == ("visit", "image_crop")
    assert registry._selection_cache[(" visit ", "image_crop", "visit", "")] is selected
    del registry._selection_cache[("visit", "image_crop")]
    assert registry.select((" visit ", "image_crop", "visit", "")) is selected
    with pytest.raises(ToolRegistryError, match="Unknown tool registry entry requested"):
        registry.select(["layout_parse"])


def test_tool_registry_select_returns_self_for_complete_selection() -> None:
    registry = built_in_tool_registry()

    selected = registry.select([" " + name + " " for name in BUILTIN_AGENTIC_TOOL_NAMES])

    assert selected is registry
    assert registry.select(BUILTIN_AGENTIC_TOOL_NAMES) is registry
    assert registry.names() == BUILTIN_AGENTIC_TOOL_NAMES


def test_tool_registry_select_exact_full_list_skips_normalization() -> None:
    class StripCountingName(str):
        strip_calls = 0

        def strip(self, chars: str | None = None) -> str:  # pragma: no cover - exact-list fast path skips this
            type(self).strip_calls += 1
            return super().strip(chars)

    registry = built_in_tool_registry()
    exact_names = [StripCountingName(name) for name in BUILTIN_AGENTIC_TOOL_NAMES]

    assert registry.select(exact_names) is registry
    assert StripCountingName.strip_calls == 0


def test_tool_registry_selection_cache_is_bounded() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    for index in range(40):
        registry._selection_cache[("visit", f"probe_{index}")] = registry

    selected = registry.select(["image_crop"])

    assert selected.names() == ("image_crop",)
    assert registry._selection_cache == {("image_crop",): selected}


def test_tool_registry_raw_tuple_alias_keeps_selection_cache_bounded() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    for index in range(31):
        registry._selection_cache[("visit", f"probe_{index}")] = registry

    selected = registry.select((" visit ", "image_crop", "visit"))

    assert selected.names() == ("visit", "image_crop")
    assert registry._selection_cache == {
        ("visit", "image_crop"): selected,
        (" visit ", "image_crop", "visit"): selected,
    }


def test_built_in_tool_config_without_names_uses_cached_serialized_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_config = built_in_tool_config()

    def fail_as_worker_tool_config(self: ToolRegistry) -> common_pb2.ToolConfig:
        raise AssertionError("built_in_tool_config() should reuse cached serialized config")

    monkeypatch.setattr(ToolRegistry, "as_worker_tool_config", fail_as_worker_tool_config)

    config = built_in_tool_config()

    assert config == expected_config
    assert config is not expected_config
    config.tools[0].name = "mutated"
    assert built_in_tool_config().tools[0].name == "image_crop"


def test_built_in_tool_config_full_selection_uses_cached_serialized_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IterCountingList(list[str]):
        iter_calls = 0

        def __iter__(self):  # pragma: no cover - exact-list fast path must not iterate
            type(self).iter_calls += 1
            return super().__iter__()

    expected_config = built_in_tool_config()

    def fail_as_worker_tool_config(self: ToolRegistry) -> common_pb2.ToolConfig:
        raise AssertionError(  # pragma: no cover
            "full built-in selection should reuse cached serialized config"
        )

    monkeypatch.setattr(ToolRegistry, "as_worker_tool_config", fail_as_worker_tool_config)

    tuple_config = built_in_tool_config(BUILTIN_AGENTIC_TOOL_NAMES)
    full_list = IterCountingList(BUILTIN_AGENTIC_TOOL_NAMES)
    list_config = built_in_tool_config(full_list)

    assert tuple_config == expected_config
    assert list_config == expected_config
    assert tuple_config is not expected_config
    assert IterCountingList.iter_calls == 0
    assert list_config is not expected_config
    tuple_config.tools[0].name = "mutated"
    assert built_in_tool_config(BUILTIN_AGENTIC_TOOL_NAMES).tools[0].name == "image_crop"


def test_built_in_tool_config_partial_selection_uses_cached_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_built_in_tool_registry() -> ToolRegistry:
        raise AssertionError(  # pragma: no cover
            "partial built_in_tool_config() should reuse the cached built-in registry"
        )

    monkeypatch.setattr(
        tool_registry_module,
        "built_in_tool_registry",
        fail_built_in_tool_registry,
    )

    config = built_in_tool_config(["image_crop", "local_compute"])

    assert [tool.name for tool in config.tools] == ["image_crop", "local_compute"]


def test_built_in_tool_config_partial_selection_reuses_serialized_selection_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_config = built_in_tool_config(["image_crop", "local_compute"])

    def fail_select(self: ToolRegistry, names: list[str] | tuple[str, ...]) -> ToolRegistry:
        raise AssertionError(  # pragma: no cover
            "cached partial built_in_tool_config() should skip registry selection"
        )

    monkeypatch.setattr(ToolRegistry, "select", fail_select)

    config = built_in_tool_config(["image_crop", "local_compute"])

    assert config == expected_config
    assert config is not expected_config
    config.tools[0].name = "mutated"
    assert built_in_tool_config(["image_crop", "local_compute"]).tools[0].name == "image_crop"


def test_tool_registry_worker_tool_config_reuses_cached_template_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = built_in_tool_registry().select(["image_crop", "local_compute"])
    expected_config = registry.as_worker_tool_config()

    def fail_as_worker_tool_definition(self: ToolDescriptor) -> common_pb2.ToolDefinition:
        raise AssertionError(  # pragma: no cover
            "as_worker_tool_config() should reuse cached config template"
        )

    def fail_from_bytes(payload: bytes) -> common_pb2.ToolConfig:
        raise AssertionError(  # pragma: no cover
            "as_worker_tool_config() should copy the cached template without reparsing bytes"
        )

    monkeypatch.setattr(ToolDescriptor, "as_worker_tool_definition", fail_as_worker_tool_definition)
    monkeypatch.setattr(tool_registry_module, "_TOOL_CONFIG_FROM_BYTES", fail_from_bytes)

    config = registry.as_worker_tool_config()

    assert config == expected_config
    assert config is not expected_config
    config.tools[0].name = "mutated"
    assert registry.as_worker_tool_config().tools[0].name == "image_crop"


def test_tool_registry_worker_tool_config_first_call_returns_isolated_copy() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    config = registry.as_worker_tool_config()
    config.tools[0].name = "mutated"

    assert registry.as_worker_tool_config().tools[0].name == "image_crop"


def test_tool_registry_exports_worker_tool_config_metadata() -> None:
    config = built_in_tool_config(["image_crop", "local_compute"])

    assert isinstance(config, common_pb2.ToolConfig)
    assert config.schema_format == "openai-function"
    assert config.schema_version == "melix.agentic_tool_registry.v1"
    assert config.toolset_version == "melix.agentic_tools.builtin.v1"
    assert config.parser == "qwen"
    assert config.parser_contract_version == "melix.tool_parser.qwen.v1"
    assert [tool.name for tool in config.tools] == ["image_crop", "local_compute"]

    crop_schema = json.loads(config.tools[0].json_schema)
    compute_schema = json.loads(config.tools[1].json_schema)
    assert crop_schema["required"] == ["media_ref", "region"]
    assert compute_schema["required"] == ["code"]


def test_tool_argument_descriptor_rejects_blank_names() -> None:
    with pytest.raises(ToolRegistryError, match="Invalid tool argument name"):
        ToolArgumentDescriptor(name=" ", json_type="string", description="Blank")


def test_tool_argument_descriptor_normalizes_exported_fields() -> None:
    argument = ToolArgumentDescriptor(
        name=" media_ref ",
        json_type=" string ",
        description=" Source image. ",
    )

    assert argument.name == "media_ref"
    assert argument.json_schema() == {
        "type": "string",
        "description": "Source image.",
    }


def test_tool_descriptor_normalizes_exported_fields_and_caches_schema() -> None:
    tool = ToolDescriptor(
        name=" image_crop ",
        description=" Crop image. ",
        tool_kind=" vision.image_crop ",
        observation_kind=" image_region ",
        arguments=(ToolArgumentDescriptor("media_ref", "string", "Source image."),),
    )

    assert tool.name == "image_crop"
    assert tool.description == "Crop image."
    assert tool.tool_kind == "vision.image_crop"
    assert tool.observation_kind == "image_region"
    assert tool.json_schema() is tool.json_schema()
    assert tool.schema_byte_count() == len(tool.json_schema().encode("utf-8"))
    assert tool.as_openai_tool()["function"]["parameters"] == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "media_ref": {
                "type": "string",
                "description": "Source image.",
            },
        },
        "required": ["media_ref"],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"name": "arg", "json_type": " ", "description": "Missing type"},
            "Tool argument arg must declare a JSON type.",
        ),
        (
            {"name": "arg", "json_type": "string", "description": " "},
            "Tool argument arg must include a description.",
        ),
        (
            {"name": "bad-name", "json_type": "string", "description": "Invalid"},
            "Invalid tool argument name: bad-name",
        ),
    ],
)
def test_tool_argument_descriptor_rejects_incomplete_contract_fields(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ToolRegistryError, match=message):
        ToolArgumentDescriptor(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"name": "Bad-Name"},
            "Invalid tool registry name: Bad-Name",
        ),
        (
            {"description": " "},
            "Tool valid_tool must include a description.",
        ),
        (
            {"tool_kind": " "},
            "Tool valid_tool must include a tool kind.",
        ),
        (
            {"observation_kind": " "},
            "Tool valid_tool must include an observation kind.",
        ),
        (
            {"arguments": ()},
            "Tool valid_tool must define at least one argument.",
        ),
        (
            {
                "arguments": (
                    ToolArgumentDescriptor("query", "string", "Query."),
                    ToolArgumentDescriptor("query", "string", "Duplicate query."),
                )
            },
            "Duplicate argument query in tool registry entry valid_tool.",
        ),
    ],
)
def test_tool_descriptor_rejects_incomplete_contract_fields(
    kwargs: dict[str, object],
    message: str,
) -> None:
    payload = {
        "name": "valid_tool",
        "description": "Valid tool.",
        "tool_kind": "test.valid",
        "observation_kind": "test_result",
        "arguments": (ToolArgumentDescriptor("query", "string", "Query."),),
    }
    payload.update(kwargs)

    with pytest.raises(ToolRegistryError, match=message):
        ToolDescriptor(**payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"schema_version": " "}, "Tool registry schema_version must be non-empty."),
        ({"toolset_version": " "}, "Tool registry toolset_version must be non-empty."),
        ({"parser": " "}, "Tool registry parser must be non-empty."),
        (
            {"parser_contract_version": " "},
            "Tool registry parser_contract_version must be non-empty.",
        ),
    ],
)
def test_tool_registry_rejects_incomplete_metadata(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ToolRegistryError, match=message):
        ToolRegistry([built_in_tool_registry().tools[0]], **kwargs)
