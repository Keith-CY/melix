from __future__ import annotations

import json

import pytest

from packages.protocol.python.worker.v1 import common_pb2

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


def test_built_in_tool_schemas_are_object_contracts_with_required_arguments() -> None:
    registry = built_in_tool_registry()

    for tool in registry.tools:
        parsed = json.loads(tool.json_schema())
        assert parsed["type"] == "object"
        assert parsed["additionalProperties"] is False
        assert parsed["required"]
        assert set(parsed["required"]).issubset(parsed["properties"])
        assert parsed["x-melix-tool-kind"] == tool.tool_kind
        assert parsed["x-melix-observation-kind"] == tool.observation_kind


def test_tool_registry_rejects_duplicate_tool_names() -> None:
    registry = built_in_tool_registry()

    with pytest.raises(ToolRegistryError, match="Duplicate tool registry entry"):
        ToolRegistry([registry.tools[0], registry.tools[0]])


def test_tool_registry_rejects_unknown_requested_names() -> None:
    registry = built_in_tool_registry()

    with pytest.raises(ToolRegistryError, match="Unknown tool registry entry requested"):
        registry.select(["image_crop", "missing_tool"])


def test_tool_registry_selects_tools_in_registry_order() -> None:
    registry = built_in_tool_registry()

    selected = registry.select(["visit", "image_crop", "visit"])

    assert selected.names() == ("image_crop", "visit")


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
    with pytest.raises(ToolRegistryError, match="Tool argument names must be non-empty"):
        ToolArgumentDescriptor(name=" ", json_type="string", description="Blank")


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
