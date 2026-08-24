from __future__ import annotations

import json
from typing import cast

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime import tool_registry as tool_registry_module
from worker.runtime.tool_registry import (
    BUILTIN_AGENTIC_TOOL_NAMES,
    ToolArgumentDescriptor,
    ToolDescriptor,
    ToolRegistry,
    ToolRegistryError,
    ToolRegistryMetrics,
    ToolSelectionInput,
    built_in_tool_config,
    built_in_tool_registry,
    select_agentic_tools_for_turn,
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
    assert "skill_lookup" not in registry.names()
    assert "memory_lookup" not in registry.names()


def test_agentic_tool_catalog_exposes_opt_in_skill_and_memory_lookup_tools() -> None:
    catalog = tool_registry_module.agentic_tool_catalog_registry()

    assert catalog.names() == tool_registry_module.SELECTABLE_AGENTIC_TOOL_NAMES
    assert catalog.metrics().tool_count == 9
    assert "skill_lookup" in catalog.names()
    assert "memory_lookup" in catalog.names()
    assert "workspace_file" in catalog.names()

    selected = catalog.select(("skill_lookup", "memory_lookup", "workspace_file"))

    assert selected.names() == ("skill_lookup", "memory_lookup", "workspace_file")
    assert [tool.tool_kind for tool in selected.tools] == [
        "skill.lookup",
        "memory.lookup",
        "workspace_file.operation",
    ]

    config = built_in_tool_config(("skill_lookup", "memory_lookup", "workspace_file"))

    assert [tool.name for tool in config.tools] == [
        "skill_lookup",
        "memory_lookup",
        "workspace_file",
    ]


def test_selectable_tool_schemas_have_index_metadata_parity() -> None:
    catalog = tool_registry_module.agentic_tool_catalog_registry()
    index_metadata = tool_registry_module.agentic_tool_index_metadata()

    schema_names = set(catalog.names())
    index_names = set(index_metadata)
    keyword_names = set(tool_registry_module._BUILTIN_TOOL_KEYWORD_HINTS)

    assert index_names == schema_names
    assert keyword_names == schema_names - set(
        tool_registry_module.ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES
    )
    for tool_name in schema_names:
        metadata = index_metadata[tool_name]
        assert metadata.tool_id == tool_name
        assert metadata.retrieval_description
        assert metadata.routing_hints or tool_name in tool_registry_module.ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES
        schema = catalog.select((tool_name,)).as_openai_tools()[0]
        assert metadata.retrieval_description == schema["function"]["description"]


def test_workspace_file_integration_intent_routes_schema_without_greeting_bleed() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=(
                "Read workspace file docs/plans/notes.md and edit the local file if the "
                "fixture says it is stale."
            ),
            vector_available=False,
            max_selected_tools=4,
        )
    )
    greeting = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Hello, can you answer briefly?",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "workspace_file")
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "workspace_file", "source": "keyword"},
    ]
    assert [schema["function"]["name"] for schema in result.registry.as_openai_tools()] == [
        "local_compute",
        "workspace_file",
    ]
    assert greeting.registry.names() == ("local_compute",)


def test_tool_schema_consistency_preflight_reports_missing_workflow_tool_without_raw_text() -> None:
    registry = tool_registry_module.agentic_tool_catalog_registry().select(("local_compute",))

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            {
                "tool_name": "visit",
                "source": "workflow_selected",
                "procedure_text": "SECRET_PROCEDURE says to visit https://example.com",
            },
        ),
        registry=registry,
        source="workflow_selected",
    )

    assert decision.consistent is False
    assert decision.referenced_tools == ("visit",)
    assert decision.missing_tools == ("visit",)
    assert decision.receipt == {
        "schema_version": "melix.agentic_tool_schema_consistency.v1",
        "toolset_version": tool_registry_module.BUILTIN_TOOLSET_VERSION,
        "outcome": "mismatch",
        "source": "workflow_selected",
        "referenced_tools": ["visit"],
        "callable_tools": ["local_compute"],
        "missing_tools": ["visit"],
        "invalid_affordance_count": 0,
        "checked_affordance_count": 1,
        "allowed_next_step": "strip_missing_affordances",
        "corrective_action": "remove_unavailable_tool_affordances",
    }
    assert "SECRET_PROCEDURE" not in json.dumps(decision.receipt, ensure_ascii=False)
    assert "https://example.com" not in json.dumps(decision.receipt, ensure_ascii=False)


def test_tool_schema_consistency_preflight_accepts_viewed_procedure_tool() -> None:
    registry = tool_registry_module.agentic_tool_catalog_registry().select(
        ("local_compute", "visit")
    )

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        ({"tool_id": "visit", "source": "viewed_procedure"},),
        registry=registry,
        source="viewed_procedure",
    )

    assert decision.consistent is True
    assert decision.referenced_tools == ("visit",)
    assert decision.missing_tools == ()
    assert decision.receipt["outcome"] == "consistent"
    assert decision.receipt["callable_tools"] == ["local_compute", "visit"]
    decision.receipt["callable_tools"].append("text_search")
    next_decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        ({"tool_id": "visit", "source": "viewed_procedure"},),
        registry=registry,
        source="viewed_procedure",
    )
    assert next_decision.receipt["callable_tools"] == ["local_compute", "visit"]
    assert decision.receipt["allowed_next_step"] == "assemble_prompt"
    assert decision.receipt["corrective_action"] == ""


def test_tool_schema_consistency_preflight_exact_builtin_name_skips_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRegex:
        def fullmatch(self, value: str):  # pragma: no cover - regression guard
            raise AssertionError(f"exact built-in affordance should skip regex: {value}")

    registry = tool_registry_module.agentic_tool_catalog_registry().select(
        ("local_compute", "visit")
    )
    monkeypatch.setattr(tool_registry_module, "_TOOL_NAME_RE", FailingRegex())

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        ({"tool_id": "visit", "source": "viewed_procedure"},),
        registry=registry,
        source="viewed_procedure",
    )

    assert decision.consistent is True
    assert decision.referenced_tools == ("visit",)
    assert decision.receipt["callable_tools"] == ["local_compute", "visit"]


def test_tool_schema_consistency_preflight_reuses_cached_name_sets() -> None:
    class CountingNames(tuple[str, ...]):
        iter_calls = 0

        def __iter__(self):
            type(self).iter_calls += 1
            return super().__iter__()

    registry = tool_registry_module.agentic_tool_catalog_registry().select(
        ("local_compute",)
    )
    catalog = tool_registry_module.agentic_tool_catalog_registry()
    object.__setattr__(catalog, "_tool_names", CountingNames(catalog.names()))

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            {"tool_id": "visit", "source": "viewed_procedure"},
            {"tool_id": "local_compute", "source": "viewed_procedure"},
        ),
        registry=registry,
        catalog=catalog,
        source="viewed_procedure",
    )

    assert decision.referenced_tools == ("visit", "local_compute")
    assert decision.missing_tools == ("visit",)
    assert CountingNames.iter_calls == 1


def test_tool_schema_consistency_preflight_reports_missing_catalog_custom_tool() -> None:
    custom_tool = ToolDescriptor(
        name="procedure_lookup",
        description="Look up an operator approved procedure by id.",
        tool_kind="procedure.lookup",
        observation_kind="procedure",
        arguments=(
            ToolArgumentDescriptor(
                name="procedure_id",
                json_type="string",
                description="Procedure identifier.",
            ),
        ),
    )
    catalog = ToolRegistry(
        (*tool_registry_module.agentic_tool_catalog_registry().tools, custom_tool)
    )
    registry = catalog.select(("local_compute",))

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            {"tool_name": "procedure_lookup", "source": "workflow_selected"},
            {"tool_name": "visit", "source": "workflow_selected"},
        ),
        registry=registry,
        catalog=catalog,
        source="workflow_selected",
    )

    assert decision.consistent is False
    assert decision.referenced_tools == ("visit", "procedure_lookup")
    assert decision.missing_tools == ("visit", "procedure_lookup")
    assert decision.receipt["invalid_affordance_count"] == 0
    assert decision.receipt["missing_tools"] == ["visit", "procedure_lookup"]


def test_tool_schema_consistency_preflight_unions_registry_only_custom_tool() -> None:
    custom_tool = ToolDescriptor(
        name="procedure_lookup",
        description="Look up an operator approved procedure by id.",
        tool_kind="procedure.lookup",
        observation_kind="procedure",
        arguments=(
            ToolArgumentDescriptor(
                name="procedure_id",
                json_type="string",
                description="Procedure identifier.",
            ),
        ),
    )
    registry = ToolRegistry((custom_tool,))
    catalog = tool_registry_module.agentic_tool_catalog_registry()

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            {"tool_name": "procedure_lookup", "source": "workflow_selected"},
            {"tool_name": "visit", "source": "workflow_selected"},
        ),
        registry=registry,
        catalog=catalog,
        source="workflow_selected",
    )

    assert decision.consistent is False
    assert decision.referenced_tools == ("visit", "procedure_lookup")
    assert decision.missing_tools == ("visit",)
    assert decision.receipt["invalid_affordance_count"] == 0


def test_tool_schema_consistency_preflight_reports_policy_disabled_context_tool() -> None:
    selection = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Visit https://example.com/docs and summarize the page.",
            vector_available=False,
            max_selected_tools=4,
            allow_web=False,
        )
    )

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        ({"tool_id": "visit", "source": "retrieved_context"},),
        registry=selection.registry,
        source="retrieved_context",
    )

    assert selection.registry.names() == ("local_compute",)
    assert decision.consistent is False
    assert decision.missing_tools == ("visit",)
    assert decision.receipt["outcome"] == "mismatch"
    assert decision.receipt["source"] == "retrieved_context"
    assert decision.receipt["missing_tools"] == ["visit"]
    assert decision.receipt["callable_tools"] == ["local_compute"]


def test_tool_schema_consistency_preflight_counts_invalid_affordances_without_echoing() -> None:
    registry = tool_registry_module.agentic_tool_catalog_registry().select(("local_compute",))

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            " local_compute ",
            "visit; SECRET_INLINE",
            {"tool_name": "bad tool SECRET_MAPPING"},
            {"name": ""},
        ),
        registry=registry,
        source="retrieved_context",
    )

    receipt_text = json.dumps(decision.receipt, ensure_ascii=False)

    assert decision.consistent is True
    assert decision.referenced_tools == ("local_compute",)
    assert decision.missing_tools == ()
    assert decision.receipt["invalid_affordance_count"] == 3
    assert decision.receipt["checked_affordance_count"] == 4
    assert "SECRET_INLINE" not in receipt_text
    assert "SECRET_MAPPING" not in receipt_text


def test_tool_schema_consistency_preflight_sanitizes_empty_invalid_batch_and_source() -> None:
    registry = tool_registry_module.agentic_tool_catalog_registry().select(("local_compute",))

    decision = tool_registry_module.preflight_agentic_tool_schema_consistency(
        (
            {"tool_id": 42},
            object(),
        ),
        registry=registry,
        source="bad source SECRET_SOURCE",
    )

    receipt_text = json.dumps(decision.receipt, ensure_ascii=False)

    assert decision.consistent is True
    assert decision.referenced_tools == ()
    assert decision.missing_tools == ()
    assert decision.receipt["source"] == "unspecified"
    assert decision.receipt["invalid_affordance_count"] == 2
    assert decision.receipt["checked_affordance_count"] == 2
    assert "SECRET_SOURCE" not in receipt_text


def test_safe_tool_affordance_source_fast_paths_common_exact_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectingToolNameRegex:
        def fullmatch(self, value: str) -> object:  # pragma: no cover
            raise AssertionError(f"unexpected regex validation for {value!r}")

    monkeypatch.setattr(tool_registry_module, "_TOOL_NAME_RE", RejectingToolNameRegex())

    assert tool_registry_module._safe_tool_affordance_source("workflow_selected") == "workflow_selected"
    assert tool_registry_module._safe_tool_affordance_source("retrieved_context") == "retrieved_context"


def test_safe_tool_affordance_source_preserves_normalized_fallback_behavior() -> None:
    assert tool_registry_module._safe_tool_affordance_source(" workflow_selected ") == "workflow_selected"
    assert tool_registry_module._safe_tool_affordance_source("bad source") == "unspecified"


def test_tool_affordance_name_exact_dict_fast_path_preserves_key_precedence() -> None:
    assert (
        tool_registry_module._tool_affordance_name(
            {"tool_name": "visit", "source": "workflow_selected"}
        )
        == "visit"
    )
    assert (
        tool_registry_module._tool_affordance_name(
            {"tool_id": "local_compute", "tool_name": "visit"}
        )
        == "local_compute"
    )
    assert (
        tool_registry_module._tool_affordance_name(
            {"tool_id": 42, "tool_name": "visit"}
        )
        is None
    )
    assert (
        tool_registry_module._tool_affordance_name({"name": "text_search"})
        == "text_search"
    )
    assert tool_registry_module._tool_affordance_name({"tool_name": 42}) is None
    assert tool_registry_module._tool_affordance_name({"name": object()}) is None
    assert (
        tool_registry_module._tool_affordance_name({"source": "workflow_selected"})
        is None
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"tool_id": " bad-name ", "retrieval_description": "Bad metadata."},
            "Invalid tool index metadata id: bad-name",
        ),
        (
            {"tool_id": "valid_tool", "retrieval_description": " "},
            "Tool index metadata valid_tool must include a retrieval description.",
        ),
    ],
)
def test_tool_index_metadata_rejects_incomplete_fields(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ToolRegistryError, match=message):
        tool_registry_module.ToolIndexMetadata(**kwargs)


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


def test_tool_registry_worker_config_reuses_cached_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    first_config = registry.as_worker_tool_config()
    first_config.tools.pop()
    first_config.schema_version = "mutated"

    def fail_as_worker_tool_definition(self: ToolDescriptor) -> common_pb2.ToolDefinition:
        raise AssertionError(  # pragma: no cover
            "cached worker tool config should copy from the cached template"
        )

    monkeypatch.setattr(ToolDescriptor, "as_worker_tool_definition", fail_as_worker_tool_definition)

    second_config = registry.as_worker_tool_config()

    assert len(second_config.tools) == len(BUILTIN_AGENTIC_TOOL_NAMES)
    assert second_config.schema_version == tool_registry_module.TOOL_REGISTRY_SCHEMA_VERSION


def test_built_in_tool_config_full_tuple_selection_returns_full_template_copy() -> None:
    selected_config = built_in_tool_config(tuple(list(BUILTIN_AGENTIC_TOOL_NAMES)))
    selected_config.tools.pop()
    selected_config.schema_version = "mutated"

    next_selected_config = built_in_tool_config(tuple(list(BUILTIN_AGENTIC_TOOL_NAMES)))

    assert [tool.name for tool in next_selected_config.tools] == list(BUILTIN_AGENTIC_TOOL_NAMES)
    assert next_selected_config.schema_version == tool_registry_module.TOOL_REGISTRY_SCHEMA_VERSION


def test_built_in_tool_config_full_list_selection_returns_full_template_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_select(self: ToolRegistry, names: tuple[str, ...]) -> object:  # pragma: no cover
        raise AssertionError("full list selection should reuse the built-in template")

    monkeypatch.setattr(ToolRegistry, "select", fail_select)

    selected_config = built_in_tool_config(list(BUILTIN_AGENTIC_TOOL_NAMES))
    selected_config.tools.pop()
    selected_config.schema_version = "mutated"

    next_selected_config = built_in_tool_config(list(BUILTIN_AGENTIC_TOOL_NAMES))

    assert [tool.name for tool in next_selected_config.tools] == list(BUILTIN_AGENTIC_TOOL_NAMES)
    assert next_selected_config.schema_version == tool_registry_module.TOOL_REGISTRY_SCHEMA_VERSION


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


def test_tool_descriptor_schema_byte_count_uses_ascii_json_length() -> None:
    tool = ToolDescriptor(
        name="summarize",
        description="Résumé summarizer",
        tool_kind="local_compute",
        observation_kind="text",
        arguments=(
            ToolArgumentDescriptor(
                name="text",
                json_type="string",
                description="Résumé input",
            ),
        ),
    )

    schema = tool.json_schema()
    assert schema.isascii()
    assert tool.schema_byte_count() == len(schema) == len(schema.encode("utf-8"))


def test_tool_registry_metrics_reuses_cached_schema_byte_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = built_in_tool_registry()
    expected_schema_bytes = sum(tool.schema_byte_count() for tool in registry.tools)

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


def test_tool_registry_empty_selection_reuses_cached_registry() -> None:
    registry = built_in_tool_registry()

    selected = registry.select([])

    assert selected.names() == ()
    assert selected.metrics().tool_count == 0
    assert selected.metrics().schema_bytes == 0
    assert selected.metrics().required_argument_count == 0
    assert registry.select(()) is selected
    assert registry.select([]) is selected


def test_tool_registry_empty_selection_uses_direct_cache_slot() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    selected = registry.select([])

    class LookupBlockedCache:
        def get(
            self,
            key: tuple[str, ...],
            default: ToolRegistry | None = None,
        ) -> ToolRegistry | None:
            raise AssertionError("empty selection should use the direct cache slot")

    registry._selection_cache = cast(
        dict[tuple[str, ...], ToolRegistry], LookupBlockedCache()
    )

    assert registry.select([]) is selected
    assert registry.select(()) is selected


def test_tool_registry_empty_selection_openai_tools_returns_fresh_empty_list() -> None:
    registry = built_in_tool_registry().select([])

    tools = registry.as_openai_tools()
    tools.append({"mutated": True})

    assert registry.as_openai_tools() == []
    assert registry.as_openai_tools() is not tools


def test_tool_registry_names_reuses_registry_snapshot() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)
    expected_names = registry.names()
    object.__setattr__(registry, "_tools", ())

    assert registry.names() is expected_names
    assert registry.names() == BUILTIN_AGENTIC_TOOL_NAMES


def test_keyword_tool_matches_reuses_compiled_rule_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_registry_module._keyword_tool_matches.cache_clear()
    expected_matches = tool_registry_module._keyword_tool_matches(
        "Search local evidence, crop the image, and visit fixture://docs/provider-contract."
    )
    tool_registry_module._keyword_tool_matches.cache_clear()
    monkeypatch.setattr(tool_registry_module, "_BUILTIN_TOOL_KEYWORD_HINT_RULES", {})

    matches = tool_registry_module._keyword_tool_matches(
        "Search local evidence, crop the image, and visit fixture://docs/provider-contract."
    )

    assert matches == expected_matches
    assert matches == ("image_crop", "text_search", "visit")


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


def test_append_selected_tool_skips_strip_for_canonical_names() -> None:
    class StripCountingName(str):
        strip_calls = 0

        def strip(self, chars: str | None = None) -> str:
            type(self).strip_calls += 1
            return super().strip(chars)

    selected_names: list[str] = []
    selected_sources: set[str] = set()
    selected_tools: list[dict[str, str]] = []
    canonical_name = StripCountingName("text_search")

    assert tool_registry_module._append_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        canonical_name,
        "keyword",
        4,
    )

    assert StripCountingName.strip_calls == 0
    assert selected_names == ["text_search"]
    assert selected_sources == {"text_search"}
    assert selected_tools == [{"tool_id": "text_search", "source": "keyword"}]

    whitespace_name = StripCountingName("  visit  ")
    assert tool_registry_module._append_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        whitespace_name,
        "keyword",
        4,
    )
    assert StripCountingName.strip_calls == 1
    assert selected_names == ["text_search", "visit"]
    assert "visit" in selected_sources
    assert selected_tools == [
        {"tool_id": "text_search", "source": "keyword"},
        {"tool_id": "visit", "source": "keyword"},
    ]

    assert not tool_registry_module._append_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        StripCountingName("   "),
        "keyword",
        4,
    )
    assert StripCountingName.strip_calls == 2
    assert selected_tools == [
        {"tool_id": "text_search", "source": "keyword"},
        {"tool_id": "visit", "source": "keyword"},
    ]


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


def test_tool_registry_select_reuses_missing_name_sentinel_between_calls() -> None:
    class DefaultRecordingIndex(dict[str, ToolDescriptor]):
        def __init__(self, values: dict[str, ToolDescriptor]) -> None:
            super().__init__(values)
            self.default_ids: list[int] = []
            self.get_calls = 0

        def get(self, key: str, default: object = None) -> ToolDescriptor | object:
            self.get_calls += 1
            self.default_ids.append(id(default))
            return super().get(key, default)

    registry = ToolRegistry(built_in_tool_registry().tools)
    index = DefaultRecordingIndex(registry._tool_by_name)
    object.__setattr__(registry, "_tool_by_name", index)

    for missing_name in ("missing_one", "missing_two"):
        with pytest.raises(ToolRegistryError, match="Unknown tool registry entry requested"):
            registry.select([missing_name])

    assert len(set(index.default_ids)) == 1
    assert index.get_calls == 2


def test_tool_registry_select_reuses_cached_selected_registry() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    selected = registry.select([" visit ", "image_crop", "visit"])

    assert registry.select(["visit", "image_crop"]) is selected
    assert selected.names() == ("visit", "image_crop")


def test_tool_registry_select_caches_single_name_fast_path() -> None:
    registry = ToolRegistry(built_in_tool_registry().tools)

    selected = registry.select((" visit ",))

    assert selected.names() == ("visit",)
    assert registry._selection_cache[("visit",)] is selected
    assert registry._selection_cache[(" visit ",)] is selected
    del registry._selection_cache[(" visit ",)]
    assert registry.select((" visit ",)) is selected
    assert registry._selection_cache[(" visit ",)] is selected
    assert registry.select(["visit"]) is selected


def test_tool_registry_exact_single_name_select_skips_normalization() -> None:
    class StripFailingName(str):
        def strip(self, chars: str | None = None) -> str:
            raise AssertionError("exact single-name selection should not strip")

    registry = ToolRegistry(built_in_tool_registry().tools)

    selected = registry.select((StripFailingName("visit"),))

    assert selected.names() == ("visit",)
    assert registry.select([StripFailingName("visit")]) is selected
    with pytest.raises(AssertionError, match="exact single-name selection"):
        StripFailingName("visit").strip()


def test_tool_registry_select_single_name_returns_self_for_single_tool_registry() -> None:
    registry = ToolRegistry((built_in_tool_registry().tools[0],))

    assert registry.select([registry.names()[0]]) is registry


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


def test_built_in_tool_config_caches_raw_normalized_selection_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_selection = (" image_crop ",)
    expected_config = built_in_tool_config(raw_selection)

    selection_templates = tool_registry_module._BUILTIN_TOOL_CONFIG_SELECTION_TEMPLATES

    assert selection_templates[raw_selection] == expected_config
    assert selection_templates[("image_crop",)] == expected_config

    def fail_select(self: ToolRegistry, names: list[str] | tuple[str, ...]) -> ToolRegistry:
        raise AssertionError(  # pragma: no cover
            "cached raw built_in_tool_config() selection should skip registry selection"
        )

    monkeypatch.setattr(ToolRegistry, "select", fail_select)

    config = built_in_tool_config(raw_selection)

    assert config == expected_config
    assert config is not expected_config
    config.tools[0].name = "mutated"
    assert built_in_tool_config(raw_selection).tools[0].name == "image_crop"


def test_tool_registry_worker_tool_config_reuses_cached_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = built_in_tool_registry().select(["image_crop", "local_compute"])
    expected_config = registry.as_worker_tool_config()

    def fail_as_worker_tool_definition(self: ToolDescriptor) -> common_pb2.ToolDefinition:
        raise AssertionError(  # pragma: no cover
            "as_worker_tool_config() should reuse the cached template"
        )

    monkeypatch.setattr(ToolDescriptor, "as_worker_tool_definition", fail_as_worker_tool_definition)

    config = registry.as_worker_tool_config()

    assert config == expected_config
    assert config is not expected_config
    config.tools[0].name = "mutated"
    assert registry.as_worker_tool_config().tools[0].name == "image_crop"


def test_agentic_tool_selection_seeds_local_compute_without_append_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appended_tool_names: list[str] = []
    original_append_selected_tool = tool_registry_module._append_selected_tool

    def tracking_append_selected_tool(
        selected_names: list[str],
        selected_sources: dict[str, str],
        selected_tools: list[dict[str, str]],
        tool_name: str,
        source: str,
        max_selected_tools: int,
    ) -> bool:
        appended_tool_names.append(tool_name)
        return original_append_selected_tool(
            selected_names,
            selected_sources,
            selected_tools,
            tool_name,
            source,
            max_selected_tools,
        )

    monkeypatch.setattr(
        tool_registry_module,
        "_append_selected_tool",
        tracking_append_selected_tool,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search the local corpus, then calculate the answer.",
            vector_selected_tool_ids=("text_search",),
            vector_available=True,
            max_selected_tools=3,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "vector"},
    ]
    assert appended_tool_names == ["text_search"]


def test_policy_agentic_tool_selection_seeds_local_compute_without_append_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appended_tool_names: list[str] = []
    original_append_selected_tool = tool_registry_module._append_policy_selected_tool

    def tracking_append_selected_tool(
        selected_names: list[str],
        selected_sources: set[str],
        selected_tools: list[dict[str, str]],
        tool_name: str,
        source: str,
        max_selected_tools: int,
        disabled_tool_names: frozenset[str] | None,
        denied_tool_names: list[str] | None,
    ) -> bool:
        appended_tool_names.append(tool_name)
        return original_append_selected_tool(
            selected_names,
            selected_sources,
            selected_tools,
            tool_name,
            source,
            max_selected_tools,
            disabled_tool_names,
            denied_tool_names,
        )

    monkeypatch.setattr(
        tool_registry_module,
        "_append_policy_selected_tool",
        tracking_append_selected_tool,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=(
                "Search local evidence, then visit fixture://docs/provider-contract "
                "without web access."
            ),
            vector_selected_tool_ids=("visit", "text_search"),
            vector_available=False,
            max_selected_tools=4,
            allow_web=False,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "keyword"},
    ]
    assert result.receipt["tool_policy_receipt"]["requested_tools"] == ["visit"]
    assert appended_tool_names == ["text_search", "visit"]


def test_agentic_tool_selection_preserves_always_available_tools_with_vector_hits() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search the local corpus, then calculate the answer.",
            vector_selected_tool_ids=("text_search",),
            vector_available=True,
            max_selected_tools=3,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt == {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": "melix.agentic_tools.builtin.v1",
        "selection_mode": "vector",
        "vector_available": True,
        "fallback_reason": "",
        "selected_tools": [
            {"tool_id": "local_compute", "source": "always"},
            {"tool_id": "text_search", "source": "vector"},
        ],
        "dropped_tool_count": 7,
        "full_schema_bytes": tool_registry_module.agentic_tool_catalog_registry()
        .metrics()
        .schema_bytes,
        "selected_schema_bytes": result.registry.metrics().schema_bytes,
    }
    assert (
        result.registry.metrics().schema_bytes
        < tool_registry_module.agentic_tool_catalog_registry().metrics().schema_bytes
    )


def test_agentic_tool_selection_caps_vector_hits_without_optional_routing() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search local evidence, then visit fixture://docs/provider-contract.",
            vector_selected_tool_ids=("text_search", "visit"),
            vector_available=True,
            max_selected_tools=2,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "vector"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "vector"},
    ]


def test_agentic_tool_selection_ignores_blank_and_duplicate_vector_hits() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search local evidence.",
            vector_selected_tool_ids=("", " text_search ", "text_search"),
            vector_available=True,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "vector"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "vector"},
    ]


def test_agentic_tool_selection_uses_builtin_name_set_for_membership() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search local evidence, then visit the cited page.",
            vector_selected_tool_ids=("unknown_tool", "text_search"),
            vector_available=True,
            max_selected_tools=4,
        )
    )

    assert tool_registry_module._BUILTIN_AGENTIC_TOOL_NAME_SET == frozenset(
        tool_registry_module.SELECTABLE_AGENTIC_TOOL_NAMES
    )
    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "vector"},
    ]


def test_agentic_tool_selection_keyword_matchable_names_omit_always_available_tool() -> None:
    assert tool_registry_module._KEYWORD_MATCHABLE_TOOL_NAMES == tuple(
        tool_name
        for tool_name in tool_registry_module.SELECTABLE_AGENTIC_TOOL_NAMES
        if tool_name not in tool_registry_module.ALWAYS_AVAILABLE_AGENTIC_TOOL_NAMES
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Run deterministic local compute for this answer.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"


def test_agentic_tool_selection_compiles_keyword_hint_rules_once_per_hint() -> None:
    compiled_rules = tool_registry_module._compile_keyword_hint_rules(
        {
            "visit": ("fixture://docs", "Visit", ""),
            "text_search": ("local evidence",),
        }
    )

    assert compiled_rules == {
        "visit": (("fixture://docs", True), (" visit ", False)),
        "text_search": ((" local evidence ", False),),
    }
    assert tool_registry_module._keyword_hint_matches(
        "Open fixture://docs/provider-contract.",
        compiled_rules["visit"][0][0],
        literal=compiled_rules["visit"][0][1],
    )
    assert tool_registry_module._keyword_hint_matches(
        "Please VISIT the cited page.",
        compiled_rules["visit"][1][0],
        literal=compiled_rules["visit"][1][1],
    )


def test_agentic_tool_selection_always_only_reuses_cached_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_select(self: ToolRegistry, names: list[str] | tuple[str, ...]) -> ToolRegistry:
        raise AssertionError(  # pragma: no cover
            f"always-only selection should reuse cached registry for {names!r}"
        )

    monkeypatch.setattr(ToolRegistry, "select", fail_select)

    result = select_agentic_tools_for_turn(ToolSelectionInput(max_selected_tools=1))

    assert result.registry is tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selected_schema_bytes"] == (
        tool_registry_module._ALWAYS_ONLY_TOOL_METRICS.schema_bytes
    )


def test_agentic_tool_selection_always_only_reuses_cached_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_metrics(self: ToolRegistry) -> ToolRegistryMetrics:
        raise AssertionError(  # pragma: no cover
            f"always-only selection should reuse cached metrics for {self!r}"
        )

    monkeypatch.setattr(ToolRegistry, "metrics", fail_metrics)

    result = select_agentic_tools_for_turn(ToolSelectionInput(max_selected_tools=1))

    assert result.registry is tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert result.receipt["dropped_tool_count"] == (
        tool_registry_module._ALWAYS_ONLY_DROPPED_TOOL_COUNT
    )
    assert result.receipt["full_schema_bytes"] == (
        tool_registry_module._AGENTIC_TOOL_CATALOG_METRICS.schema_bytes
    )
    assert result.receipt["selected_schema_bytes"] == (
        tool_registry_module._ALWAYS_ONLY_TOOL_METRICS.schema_bytes
    )


def test_agentic_tool_selection_no_keyword_fallback_reuses_always_only_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_select(self: ToolRegistry, names: list[str] | tuple[str, ...]) -> ToolRegistry:
        raise AssertionError(  # pragma: no cover
            f"no-keyword fallback should reuse cached registry for {names!r}"
        )

    def fail_metrics(self: ToolRegistry) -> ToolRegistryMetrics:
        raise AssertionError(  # pragma: no cover
            f"no-keyword fallback should reuse cached metrics for {self!r}"
        )

    monkeypatch.setattr(ToolRegistry, "select", fail_select)
    monkeypatch.setattr(ToolRegistry, "metrics", fail_metrics)

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry is tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert result.receipt == {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": "melix.agentic_tools.builtin.v1",
        "selection_mode": "fallback",
        "vector_available": False,
        "fallback_reason": "no_keyword_match",
        "selected_tools": [{"tool_id": "local_compute", "source": "always"}],
        "dropped_tool_count": tool_registry_module._ALWAYS_ONLY_DROPPED_TOOL_COUNT,
        "full_schema_bytes": tool_registry_module._AGENTIC_TOOL_CATALOG_METRICS.schema_bytes,
        "selected_schema_bytes": tool_registry_module._ALWAYS_ONLY_TOOL_METRICS.schema_bytes,
    }

    context_result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer briefly.",
            recent_user_turns=("Discuss cropland.",),
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert context_result.registry is tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert context_result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]

    invalid_vector_result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer briefly.",
            recent_user_turns=("Discuss cropland.",),
            vector_selected_tool_ids=("unknown_tool",),
            vector_available=True,
            max_selected_tools=4,
        )
    )

    assert invalid_vector_result.registry is tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert invalid_vector_result.receipt["vector_available"] is True
    assert invalid_vector_result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]


def test_agentic_tool_selection_always_only_receipts_are_isolated() -> None:
    first_result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            vector_available=False,
            max_selected_tools=4,
        )
    )
    first_result.receipt["selected_tools"][0]["tool_id"] = "mutated"
    first_result.receipt["selected_tools"].append(
        {"tool_id": "mutated", "source": "test"}
    )

    second_result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert second_result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]


def test_agentic_tool_selection_always_only_supports_custom_registry() -> None:
    registry = ToolRegistry(tool_registry_module.agentic_tool_catalog_registry().tools)

    result = tool_registry_module._build_always_only_tool_selection_result(
        registry,
        ToolSelectionInput(vector_available=True),
    )

    assert result.registry is registry.select(("local_compute",))
    assert result.registry is not tool_registry_module._ALWAYS_ONLY_TOOL_REGISTRY
    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]


def test_agentic_tool_selection_max_always_only_skips_optional_routing_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_keyword_tool_matches(text: str) -> tuple[str, ...]:  # pragma: no cover
        raise AssertionError("always-only selection should skip keyword scans")

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        fail_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search the local text evidence and visit fixture://docs/provider-contract.",
            recent_user_turns=("Crop the image region.",),
            vector_selected_tool_ids=("text_search", "visit"),
            vector_available=True,
            max_selected_tools=1,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt == {
        "schema_version": "melix.agentic_tool_selection.v1",
        "toolset_version": "melix.agentic_tools.builtin.v1",
        "selection_mode": "fallback",
        "vector_available": True,
        "fallback_reason": "no_keyword_match",
        "selected_tools": [{"tool_id": "local_compute", "source": "always"}],
        "dropped_tool_count": 8,
        "full_schema_bytes": tool_registry_module.agentic_tool_catalog_registry()
        .metrics()
        .schema_bytes,
        "selected_schema_bytes": result.registry.metrics().schema_bytes,
    }


def test_agentic_tool_selection_uses_keyword_fallback_when_vector_unavailable() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Open fixture://docs/provider-contract and summarize the page.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "visit")
    assert result.receipt["selection_mode"] == "keyword"
    assert result.receipt["vector_available"] is False
    assert result.receipt["fallback_reason"] == "vector_unavailable"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "visit", "source": "keyword"},
    ]


def test_agentic_tool_selection_explicit_web_deny_blocks_keyword_visit_with_policy_receipt() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Visit https://example.com/docs and summarize the page.",
            vector_available=False,
            max_selected_tools=4,
            allow_web=False,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "policy_disabled"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]
    assert result.receipt["tool_policy_receipt"] == {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": False,
        "explicit_allows": [],
        "explicit_denies": ["web"],
        "resolved_disabled_tools": ["visit"],
        "requested_tools": ["visit"],
    }
    result.receipt["tool_policy_receipt"]["explicit_denies"].append("mutated")
    result.receipt["tool_policy_receipt"]["resolved_disabled_tools"].append("mutated")
    result.receipt["tool_policy_receipt"]["requested_tools"].append("mutated")
    repeated = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Visit https://example.com/docs and summarize the page.",
            vector_available=False,
            max_selected_tools=4,
            allow_web=False,
        )
    )
    assert repeated.receipt["tool_policy_receipt"] == {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": False,
        "explicit_allows": [],
        "explicit_denies": ["web"],
        "resolved_disabled_tools": ["visit"],
        "requested_tools": ["visit"],
    }
    assert "https://example.com" not in json.dumps(result.receipt)


def test_agentic_policy_append_rejects_invalid_duplicate_and_denied_tools() -> None:
    selected_names: list[str] = []
    selected_sources: set[str] = set()
    selected_tools: list[dict[str, str]] = []
    denied_tool_names: list[str] = []

    assert not tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        "",
        "vector",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )
    assert not tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        " \t ",
        "vector",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )
    assert not tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        "missing_tool",
        "vector",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )
    assert tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        "local_compute",
        "always",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )
    assert not tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        "local_compute",
        "keyword",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )
    assert not tool_registry_module._append_policy_selected_tool(
        selected_names,
        selected_sources,
        selected_tools,
        " visit ",
        "keyword",
        4,
        frozenset({"visit"}),
        denied_tool_names,
    )

    assert selected_names == ["local_compute"]
    assert selected_tools == [{"tool_id": "local_compute", "source": "always"}]
    assert denied_tool_names == ["visit"]


def test_agentic_tool_policy_receipt_is_absent_without_explicit_policy() -> None:
    assert (
        tool_registry_module._agentic_tool_policy_receipt(
            ToolSelectionInput(current_user_turn="Search local evidence."),
            None,
            None,
        )
        is None
    )


def test_agentic_tool_selection_explicit_web_deny_max_always_only_records_policy() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Visit https://example.com/docs and summarize the page.",
            vector_selected_tool_ids=("visit",),
            vector_available=True,
            max_selected_tools=1,
            allow_web=False,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]
    assert result.receipt["tool_policy_receipt"] == {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": False,
        "explicit_allows": [],
        "explicit_denies": ["web"],
        "resolved_disabled_tools": ["visit"],
        "requested_tools": [],
    }


def test_agentic_tool_selection_explicit_web_deny_blocks_vector_visit_with_policy_receipt() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Summarize the cited page.",
            vector_selected_tool_ids=("visit",),
            vector_available=True,
            max_selected_tools=4,
            allow_web=False,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "policy_disabled"
    assert result.receipt["tool_policy_receipt"] == {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": False,
        "explicit_allows": [],
        "explicit_denies": ["web"],
        "resolved_disabled_tools": ["visit"],
        "requested_tools": ["visit"],
    }


def test_agentic_tool_selection_explicit_web_allow_whitespace_turn_records_policy() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=" \t\n  ",
            vector_available=False,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "no_keyword_match"
    assert result.receipt["tool_policy_receipt"]["explicit_allows"] == ["web"]


def test_agentic_tool_selection_explicit_web_allow_no_keyword_current_falls_back() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            vector_available=False,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["fallback_reason"] == "no_keyword_match"
    assert result.receipt["tool_policy_receipt"]["allow_web"] is True


def test_agentic_tool_selection_explicit_web_allow_context_without_keywords_falls_back() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            recent_user_turns=("Prior note without tool hints.",),
            vector_available=False,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["fallback_reason"] == "no_keyword_match"
    assert result.receipt["tool_policy_receipt"]["allow_web"] is True


def test_agentic_tool_selection_explicit_web_allow_recent_context_keyword_selects_tool() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Use two results this time.",
            recent_user_turns=("Search the local text evidence.",),
            vector_available=False,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "keyword"
    assert result.receipt["fallback_reason"] == "vector_unavailable"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "keyword_context"},
    ]
    assert result.receipt["tool_policy_receipt"]["allow_web"] is True


def test_agentic_tool_selection_explicit_web_allow_vector_selection_returns_vector() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Summarize the cited evidence.",
            vector_selected_tool_ids=("text_search",),
            vector_available=True,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "vector"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "vector"},
    ]
    assert result.receipt["tool_policy_receipt"]["explicit_allows"] == ["web"]


def test_agentic_tool_selection_explicit_web_allow_records_policy_without_disabling_visit() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Visit fixture://docs/provider-contract and summarize the page.",
            vector_available=False,
            max_selected_tools=4,
            allow_web=True,
        )
    )

    assert result.registry.names() == ("local_compute", "visit")
    assert result.receipt["selection_mode"] == "keyword"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "visit", "source": "keyword"},
    ]
    assert result.receipt["tool_policy_receipt"] == {
        "schema_version": "melix.agentic_tool_policy.v1",
        "allow_web": True,
        "explicit_allows": ["web"],
        "explicit_denies": [],
        "resolved_disabled_tools": [],
        "requested_tools": [],
    }


def test_agentic_tool_selection_whitespace_turn_skips_casefold() -> None:
    class CasefoldFailingWhitespace(str):
        def casefold(self) -> str:  # pragma: no cover - must not be called
            raise AssertionError("whitespace-only turns should skip casefold")

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=CasefoldFailingWhitespace(" \t\n  "),
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "no_keyword_match"


def test_agentic_tool_selection_whitespace_turn_skips_keyword_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_keyword_tool_matches(text: str) -> tuple[str, ...]:  # pragma: no cover
        raise AssertionError(f"whitespace fast path should not scan keywords: {text!r}")

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        fail_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=" \t\n  ",
            vector_available=True,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["vector_available"] is True
    assert result.receipt["fallback_reason"] == "no_keyword_match"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
    ]


def test_agentic_tool_selection_skips_empty_context_keyword_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_texts: list[str] = []
    real_keyword_tool_matches = tool_registry_module._keyword_tool_matches

    def record_keyword_tool_matches(text: str) -> tuple[str, ...]:
        scanned_texts.append(text)
        return real_keyword_tool_matches(text)

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        record_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Open fixture://docs/provider-contract and summarize the page.",
            vector_available=False,
            recent_user_turns=(),
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "visit")
    assert scanned_texts == ["Open fixture://docs/provider-contract and summarize the page."]


def test_agentic_tool_selection_blank_current_turn_scans_recent_context_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_texts: list[str] = []
    real_keyword_tool_matches = tool_registry_module._keyword_tool_matches

    def record_keyword_tool_matches(text: str) -> tuple[str, ...]:
        scanned_texts.append(text)
        return real_keyword_tool_matches(text)

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        record_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=" \t\n  ",
            vector_available=False,
            recent_user_turns=("Search the local text evidence.",),
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "keyword"
    assert scanned_texts == ["Search the local text evidence."]


def test_agentic_tool_selection_skips_context_scan_when_current_fills_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_texts: list[str] = []
    real_keyword_tool_matches = tool_registry_module._keyword_tool_matches

    def record_keyword_tool_matches(text: str) -> tuple[str, ...]:
        scanned_texts.append(text)
        return real_keyword_tool_matches(text)

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        record_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search the local text evidence.",
            vector_available=False,
            recent_user_turns=("Visit fixture://docs/provider-contract.",),
            max_selected_tools=2,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "keyword"
    assert scanned_texts == ["Search the local text evidence."]


def test_agentic_tool_selection_reuses_single_recent_context_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_text_ids: list[int] = []
    recent_context = "Search the local text evidence."
    real_keyword_tool_matches = tool_registry_module._keyword_tool_matches

    def record_keyword_tool_matches(text: str) -> tuple[str, ...]:
        scanned_text_ids.append(id(text))
        return real_keyword_tool_matches(text)

    monkeypatch.setattr(
        tool_registry_module,
        "_keyword_tool_matches",
        record_keyword_tool_matches,
    )

    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Use two results this time.",
            vector_available=False,
            recent_user_turns=(recent_context,),
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert len(scanned_text_ids) == 2
    assert scanned_text_ids[1] == id(recent_context)


def test_agentic_tool_selection_joins_multiple_recent_context_turns() -> None:
    assert tool_registry_module._recent_user_turns_keyword_context(
        ("Search the local text evidence.", "Visit fixture://docs/provider-contract.")
    ) == "Search the local text evidence. Visit fixture://docs/provider-contract."


@pytest.mark.parametrize(
    ("current_user_turn", "expected_tool"),
    [
        ("Search, then summarize the local evidence.", "text_search"),
        ("Open: fixture://docs/provider-contract.", "visit"),
        ("Crop-region from img-1 so the sign is readable.", "image_crop"),
    ],
)
def test_agentic_tool_selection_keyword_fallback_handles_adjacent_punctuation(
    current_user_turn: str,
    expected_tool: str,
) -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=current_user_turn,
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert expected_tool in result.registry.names()
    assert result.receipt["selection_mode"] == "keyword"


def test_agentic_tool_selection_keyword_fallback_ignores_embedded_words() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer the researcher briefly about cropland.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"


def test_agentic_tool_selection_keyword_fallback_keeps_multiple_punctuated_tools() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Search, then crop-region from img-1.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "image_crop", "text_search")
    assert result.receipt["selection_mode"] == "keyword"


@pytest.mark.parametrize(
    ("current_user_turn", "expected_tool"),
    [
        ("Find the best repo skill for this task.", "skill_lookup"),
        ("Look up pinned memory for this operator preference.", "memory_lookup"),
    ],
)
def test_agentic_tool_selection_keyword_fallback_selects_skill_and_memory_lookup(
    current_user_turn: str,
    expected_tool: str,
) -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=current_user_turn,
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", expected_tool)
    assert result.receipt["selection_mode"] == "keyword"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": expected_tool, "source": "keyword"},
    ]


def test_agentic_tool_selection_keyword_matcher_ignores_empty_hints() -> None:
    assert tool_registry_module._keyword_hint_matches("search local evidence", "") is False


def test_agentic_tool_selection_keyword_matcher_covers_literal_and_boundary_branches() -> None:
    assert tool_registry_module._keyword_hint_matches(
        "open fixture://docs/provider-contract",
        "fixture://",
    )
    assert not tool_registry_module._keyword_hint_matches(
        "open local documentation",
        "fixture://",
    )
    assert tool_registry_module._keyword_hint_matches(
        "Search, then crop-region.",
        "crop",
    )
    assert tool_registry_module._keyword_hint_matches(
        "search local evidence",
        " search ",
        literal=False,
        boundary_text=" search local evidence ",
    )


def test_agentic_tool_selection_keyword_matches_reuse_bounded_cache() -> None:
    matcher = tool_registry_module._keyword_tool_matches
    matcher.cache_clear()

    assert matcher("Search, then crop-region.") == ("image_crop", "text_search")
    first_info = matcher.cache_info()
    assert matcher("Search, then crop-region.") == ("image_crop", "text_search")
    second_info = matcher.cache_info()

    assert first_info.maxsize == 128
    assert first_info.misses == 1
    assert second_info.hits == first_info.hits + 1


def test_agentic_tool_selection_keyword_matches_preserve_non_ascii_ascii_hint() -> None:
    matcher = tool_registry_module._keyword_tool_matches
    matcher.cache_clear()

    assert matcher("Please SEARCH café evidence.") == ("text_search",)


def test_agentic_tool_selection_keyword_rule_compiler_filters_empty_hints() -> None:
    rules = tool_registry_module._compile_keyword_hint_rules(
        {
            "visit": ("fixture://", ""),
            "text_search": ("Search",),
        }
    )

    assert rules == {
        "visit": (("fixture://", True),),
        "text_search": ((" search ", False),),
    }


def test_agentic_tool_selection_uses_recent_context_for_short_followup() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Use two results this time.",
            recent_user_turns=("Search the local text evidence for runtime startup receipts.",),
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute", "text_search")
    assert result.receipt["selection_mode"] == "keyword"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"},
        {"tool_id": "text_search", "source": "keyword_context"},
    ]


def test_agentic_tool_selection_records_fallback_when_no_keyword_matches() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn="Answer briefly.",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "no_keyword_match"
    assert result.receipt["selected_tools"] == [
        {"tool_id": "local_compute", "source": "always"}
    ]


def test_tool_selection_receipt_reuses_bound_metric_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tool_registry_module.agentic_tool_catalog_registry()
    original_metrics = ToolRegistry.metrics
    metrics_call_count = 0

    def counted_metrics(self: ToolRegistry) -> object:
        nonlocal metrics_call_count
        metrics_call_count += 1
        return original_metrics(self)

    monkeypatch.setattr(ToolRegistry, "metrics", counted_metrics)

    result = tool_registry_module._build_tool_selection_result(
        registry,
        ["local_compute", "text_search"],
        {"local_compute": "always", "text_search": "keyword"},
        ToolSelectionInput(
            current_user_turn="Search local evidence.",
            vector_available=False,
            max_selected_tools=4,
        ),
        "keyword",
        "vector_unavailable",
    )

    assert result.receipt["full_schema_bytes"] >= result.receipt["selected_schema_bytes"]
    assert metrics_call_count == 2


def test_agentic_tool_selection_records_fallback_for_whitespace_only_turn() -> None:
    result = select_agentic_tools_for_turn(
        ToolSelectionInput(
            current_user_turn=" \t\n ",
            vector_available=False,
            max_selected_tools=4,
        )
    )

    assert result.registry.names() == ("local_compute",)
    assert result.receipt["selection_mode"] == "fallback"
    assert result.receipt["fallback_reason"] == "no_keyword_match"


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
