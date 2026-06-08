from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.runtime.agentic_tools import AgenticToolRuntimeError, _context_list, execute_agentic_tool_calls
from worker.runtime.tool_observation import ToolObservationPolicy


_BUILT_IN_TOOL_CALLS = (
    ("image_crop", {"media_ref": "img-1", "region": "sign"}),
    ("layout_parse", {"media_ref": "img-1"}),
    ("text_search", {"query": "melix"}),
    ("image_search", {"query": "receipt"}),
    ("visit", {"url": "fixture://page-1"}),
    ("local_compute", {"code": "2 + 3 * 4"}),
)


def test_agentic_tool_runtime_executes_all_builtin_tools_with_shared_observation_shape() -> None:
    run = execute_agentic_tool_calls(
        [
            {"id": "crop-1", "name": "image_crop", "arguments": {"media_ref": "img-1", "region": "sign"}},
            {"id": "layout-1", "name": "layout_parse", "arguments": {"media_ref": "img-1"}},
            {"id": "text-1", "name": "text_search", "arguments": {"query": "melix"}},
            {"id": "image-1", "name": "image_search", "arguments": {"query": "receipt"}},
            {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://page-1"}},
            {"id": "compute-1", "name": "local_compute", "arguments": {"code": "2 + 3 * 4"}},
        ],
        fixture_context={
            "crops": {"img-1#sign": {"text": "MELIX LABS"}},
            "layouts": {"img-1": [{"kind": "text", "text": "MELIX LABS"}]},
            "text_corpus": [{"id": "doc-1", "text": "Melix local tool runtime."}],
            "image_corpus": [{"id": "image-doc-1", "media_ref": "img-1", "caption": "receipt scan"}],
            "pages": {"fixture://page-1": {"title": "Fixture Page", "text": "Visited page."}},
        },
    )

    assert run.registry_receipt["toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert run.metrics["agentic_tool.call_count"] == 6.0
    assert run.metrics["agentic_tool.completed_count"] == 6.0
    assert run.metrics["agentic_tool.latency_ms"] >= 0.0
    assert [observation["status"] for observation in run.observations] == ["completed"] * 6
    assert run.observations[-1]["payload"]["result"] == 14
    assert len(run.trace_turns) == 12
    assert "melix.agentic_tool_observation.v1" in json.dumps(run.to_sample_evidence())


def test_agentic_tool_runtime_records_timeout_and_failed_statuses() -> None:
    run = execute_agentic_tool_calls(
        [
            {"id": "timeout-1", "name": "local_compute", "arguments": {"code": "timeout"}},
            {"id": "failed-1", "name": "local_compute", "arguments": {"code": "__import__('os')"}},
        ],
    )

    assert [observation["status"] for observation in run.observations] == ["timeout", "failed"]
    assert run.metrics["agentic_tool.timeout_count"] == 1.0
    assert run.metrics["agentic_tool.failed_count"] == 1.0
    assert "only supports deterministic arithmetic" in run.observations[1]["payload"]["error"]


@pytest.mark.parametrize(("tool_name", "arguments"), _BUILT_IN_TOOL_CALLS)
@pytest.mark.parametrize(
    ("override", "expected_status", "expected_failure_stage", "expected_cancelled"),
    [
        ({"status": "timeout", "message": "forced timeout"}, "timeout", "tool_timeout", False),
        ({"status": "failed", "failure_stage": "fixture_failure"}, "failed", "fixture_failure", False),
        ({"status": "cancelled"}, "failed", "cancelled", True),
    ],
)
def test_agentic_tool_runtime_applies_status_controls_to_every_adapter(
    tool_name: str,
    arguments: dict[str, object],
    override: dict[str, str],
    expected_status: str,
    expected_failure_stage: str,
    expected_cancelled: bool,
) -> None:
    run = execute_agentic_tool_calls(
        [{"id": f"{tool_name}-1", "name": tool_name, "arguments": arguments}],
        fixture_context={"tool_status_overrides": {tool_name: override}},
        observation_policy=ToolObservationPolicy(timeout_ms=250),
    )

    observation = run.observations[0]
    assert observation["status"] == expected_status
    assert observation["payload"]["failure_stage"] == expected_failure_stage
    assert bool(observation["payload"].get("cancelled", False)) is expected_cancelled
    assert run.metrics["agentic_tool.timeout_count"] == float(expected_status == "timeout")
    assert run.metrics["agentic_tool.failed_count"] == float(expected_status == "failed")
    if expected_status == "timeout":
        assert observation["timeout_ms"] == 250


def test_agentic_tool_runtime_prefers_call_id_status_control_over_tool_status() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "visit-special", "name": "visit", "arguments": {"url": "fixture://page-1"}}],
        fixture_context={
            "tool_status_overrides": {
                "visit": {"status": "timeout"},
                "visit-special": {"status": "failed", "failure_stage": "call_specific_failure"},
            }
        },
    )

    assert run.observations[0]["status"] == "failed"
    assert run.observations[0]["payload"]["failure_stage"] == "call_specific_failure"


def test_agentic_tool_runtime_accepts_wildcard_string_status_control() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://page-1"}}],
        fixture_context={"tool_status_overrides": {"*": "timeout"}},
    )

    assert run.observations[0]["status"] == "timeout"
    assert run.observations[0]["payload"]["failure_stage"] == "tool_timeout"


def test_agentic_tool_runtime_covers_edge_payload_branches() -> None:
    run = execute_agentic_tool_calls(
        [
            {"id": "tuple-1", "name": "text_search", "arguments": {"query": "alpha", "max_results": 1}},
            {"id": "image-1", "name": "image_search", "arguments": {"query": "receipt", "max_results": 1}},
            {"id": "missing-visit", "name": "visit", "arguments": {"url": "fixture://missing"}},
            {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://text"}},
            {"id": "layout-1", "name": "layout_parse", "arguments": {"media_ref": "empty-layout"}},
            {
                "id": "crop-1",
                "name": "image_crop",
                "arguments": {"media_ref": "img-2", "region": "whole", "purpose": "read label"},
            },
            {"id": "div-1", "name": "local_compute", "arguments": {"code": "8 / 2"}},
            {"id": "neg-1", "name": "local_compute", "arguments": {"code": "-3 + 5"}},
            {"id": "zero-1", "name": "local_compute", "arguments": {"code": "1 / 0"}},
        ],
        fixture_context={
            "text_corpus": {
                "default": [
                    {"id": "doc-1", "text": "alpha beta"},
                    {"id": "doc-2", "text": "alpha gamma"},
                ]
            },
            "image_corpus": {
                "default": [
                    {"id": "image-1", "media_ref": "img-1", "caption": "receipt front"},
                    {"id": "image-2", "media_ref": "img-2", "caption": "receipt back"},
                ]
            },
            "pages": {"fixture://text": "plain page"},
            "layouts": {"empty-layout": []},
            "crops": {"img-2": "raw crop text"},
        },
    )

    assert run.observations[0]["payload"]["result_count"] == 1
    assert run.observations[1]["payload"]["results"][0]["media_ref"] == "img-1"
    assert run.observations[2]["payload"]["found"] is False
    assert run.observations[3]["payload"]["text"] == "plain page"
    assert run.observations[4]["payload"]["elements"] == []
    assert run.observations[5]["payload"]["purpose"] == "read label"
    assert run.observations[6]["payload"]["result"] == 4
    assert run.observations[7]["payload"]["result"] == 2
    assert run.observations[8]["status"] == "failed"


def test_agentic_tool_runtime_preserves_non_typed_execution_errors() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "syntax-1", "name": "local_compute", "arguments": {"code": "("}}],
    )

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert "never closed" in observation["payload"]["error"]


@pytest.mark.parametrize(
    "tool_calls",
    [
        [object()],
        [{"arguments": {}}],
        [{"name": "local_compute", "arguments": []}],
    ],
)
def test_agentic_tool_runtime_rejects_malformed_tool_calls(tool_calls: list[object]) -> None:
    with pytest.raises(AgenticToolRuntimeError):
        execute_agentic_tool_calls(tool_calls)


def test_agentic_tool_runtime_rejects_missing_required_arguments() -> None:
    with pytest.raises(AgenticToolRuntimeError, match="Missing required arguments for image_crop"):
        execute_agentic_tool_calls([{"name": "image_crop", "arguments": {"media_ref": "img-1"}}])


def test_agentic_tool_runtime_rejects_invalid_status_controls() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://page-1"}}],
        fixture_context={"tool_status_overrides": {"visit": {"status": "paused"}}},
    )

    assert run.observations[0]["status"] == "failed"
    assert "Unsupported agentic tool status override" in run.observations[0]["payload"]["error"]


def test_agentic_tool_runtime_rejects_non_object_status_controls() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://page-1"}}],
        fixture_context={"tool_status_overrides": {"visit": 42}},
    )

    assert run.observations[0]["status"] == "failed"
    assert "status override must be a string or JSON object" in run.observations[0]["payload"]["error"]


@pytest.mark.parametrize(
    ("tool_call", "fixture_context", "expected_field", "expected_source_type", "expected_source_id"),
    [
        (
            {"id": "visit-arg", "name": "visit", "arguments": {"url": {"not": "a url"}}},
            {},
            "arguments.url",
            "tool_argument",
            "visit-arg",
        ),
        (
            {"id": "visit-page", "name": "visit", "arguments": {"url": "fixture://bad-page"}},
            {"pages": {"fixture://bad-page": {"title": "Bad Page", "text": ["not", "text"]}}},
            "pages.text",
            "retrieved_page",
            "fixture://bad-page",
        ),
        (
            {"id": "text-doc", "name": "text_search", "arguments": {"query": "melix"}},
            {"text_corpus": [{"id": "doc-bad", "text": {"nested": "instruction"}}]},
            "text_corpus.text",
            "retrieved_document",
            "doc-bad",
        ),
        (
            {"id": "status-message", "name": "visit", "arguments": {"url": "fixture://page"}},
            {"tool_status_overrides": {"visit": {"status": "failed", "message": ["not", "text"]}}},
            "tool_status_overrides.message",
            "tool_status_override",
            "visit",
        ),
        (
            {
                "id": "layout-detail",
                "name": "layout_parse",
                "arguments": {"media_ref": "img-1", "detail_level": ["not", "string"]},
            },
            {},
            "arguments.detail_level",
            "tool_argument",
            "layout-detail",
        ),
        (
            {
                "id": "crop-purpose",
                "name": "image_crop",
                "arguments": {"media_ref": "img-1", "region": "whole", "purpose": []},
            },
            {},
            "arguments.purpose",
            "tool_argument",
            "crop-purpose",
        ),
    ],
)
def test_agentic_tool_runtime_fails_closed_for_invalid_untrusted_value_types(
    tool_call: dict[str, object],
    fixture_context: dict[str, object],
    expected_field: str,
    expected_source_type: str,
    expected_source_id: str,
) -> None:
    run = execute_agentic_tool_calls([tool_call], fixture_context=fixture_context)

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "invalid_untrusted_input_type"
    assert observation["payload"]["field"] == expected_field
    assert observation["payload"]["source_type"] == expected_source_type
    assert observation["payload"]["source_id"] == expected_source_id
    assert observation["payload"]["expected_type"] == "str"
    assert observation["payload"]["corrective_action"] == "Provide this untrusted value as a JSON string."
    assert run.metrics["agentic_tool.failed_count"] == 1.0


@pytest.mark.parametrize(
    (
        "tool_call",
        "fixture_context",
        "expected_field",
        "expected_source_type",
        "expected_source_id",
        "expected_type",
        "actual_type",
    ),
    [
        (
            {"id": "layout-container", "name": "layout_parse", "arguments": {"media_ref": "img-bad"}},
            {"layouts": {"img-bad": {"not": "layout elements"}}},
            "layouts",
            "retrieved_layout",
            "img-bad",
            "list",
            "dict",
        ),
        (
            {"id": "crop-list", "name": "image_crop", "arguments": {"media_ref": "img-2", "region": "whole"}},
            {"crops": {"img-2#whole": ["not", "crop text"]}},
            "crops.text",
            "retrieved_crop",
            "img-2#whole",
            "str",
            "list",
        ),
    ],
)
def test_agentic_tool_runtime_fails_closed_for_invalid_layout_and_crop_payloads(
    tool_call: dict[str, object],
    fixture_context: dict[str, object],
    expected_field: str,
    expected_source_type: str,
    expected_source_id: str,
    expected_type: str,
    actual_type: str,
) -> None:
    run = execute_agentic_tool_calls([tool_call], fixture_context=fixture_context)

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "invalid_untrusted_input_type"
    assert observation["payload"]["field"] == expected_field
    assert observation["payload"]["source_type"] == expected_source_type
    assert observation["payload"]["source_id"] == expected_source_id
    assert observation["payload"]["expected_type"] == expected_type
    assert observation["payload"]["actual_type"] == actual_type


@pytest.mark.parametrize(
    (
        "tool_call",
        "fixture_context",
        "expected_field",
        "expected_source_type",
        "expected_source_id",
        "expected_type",
        "actual_type",
    ),
    [
        (
            {"id": "text-corpus-container", "name": "text_search", "arguments": {"query": "melix"}},
            {"text_corpus": {"default": {"not": "a corpus list"}}},
            "text_corpus",
            "retrieved_corpus",
            "default",
            "list",
            "dict",
        ),
        (
            {"id": "image-corpus-row", "name": "image_search", "arguments": {"query": "receipt"}},
            {"image_corpus": [{"id": "image-1", "media_ref": "img-1", "caption": "receipt"}, ["not", "row"]]},
            "image_corpus.item",
            "retrieved_image",
            "image-2",
            "object",
            "list",
        ),
    ],
)
def test_agentic_tool_runtime_fails_closed_for_invalid_corpus_containers_and_rows(
    tool_call: dict[str, object],
    fixture_context: dict[str, object],
    expected_field: str,
    expected_source_type: str,
    expected_source_id: str,
    expected_type: str,
    actual_type: str,
) -> None:
    run = execute_agentic_tool_calls([tool_call], fixture_context=fixture_context)

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "invalid_untrusted_input_type"
    assert observation["payload"]["field"] == expected_field
    assert observation["payload"]["source_type"] == expected_source_type
    assert observation["payload"]["source_id"] == expected_source_id
    assert observation["payload"]["expected_type"] == expected_type
    assert observation["payload"]["actual_type"] == actual_type


def test_agentic_tool_runtime_rejects_unknown_corpus_keys_before_defaulting_source_metadata() -> None:
    with pytest.raises(AgenticToolRuntimeError, match="Unsupported retrieved corpus key: audio_corpus"):
        _context_list({"audio_corpus": [{"id": "clip-1"}]}, "audio_corpus", "default")


@pytest.mark.parametrize(
    (
        "tool_call",
        "fixture_context",
        "expected_source_type",
        "expected_source_id",
        "expected_privilege",
    ),
    [
        (
            {"id": "text-owner", "name": "text_search", "arguments": {"query": "melix"}},
            {
                "owner_scope": {"expected_owner_id": "operator-a"},
                "text_corpus": [
                    {
                        "id": "doc-owner-b",
                        "owner_id": "operator-b",
                        "privilege": "read",
                        "text": "Melix private note.",
                    }
                ],
            },
            "retrieved_document",
            "doc-owner-b",
            "read",
        ),
        (
            {"id": "image-owner", "name": "image_search", "arguments": {"query": "receipt"}},
            {
                "owner_scope": {"expected_owner_id": "operator-a", "privilege": "viewer"},
                "image_corpus": [
                    {
                        "id": "image-owner-b",
                        "owner_id": "operator-b",
                        "media_ref": "img-private",
                        "caption": "receipt",
                    }
                ],
            },
            "retrieved_image",
            "image-owner-b",
            "viewer",
        ),
        (
            {"id": "visit-owner", "name": "visit", "arguments": {"url": "fixture://private-page"}},
            {
                "owner_scope": {"expected_owner_id": "operator-a"},
                "pages": {
                    "fixture://private-page": {
                        "owner_id": "operator-b",
                        "privilege": "read",
                        "title": "Private Page",
                        "text": "Cross owner page.",
                    }
                },
            },
            "retrieved_page",
            "fixture://private-page",
            "read",
        ),
        (
            {"id": "layout-owner", "name": "layout_parse", "arguments": {"media_ref": "img-private"}},
            {
                "owner_scope": {"expected_owner_id": "operator-a"},
                "layouts": {
                    "img-private": {
                        "owner_id": "operator-b",
                        "privilege": "inspect",
                        "elements": [{"kind": "text", "text": "private"}],
                    }
                },
            },
            "retrieved_layout",
            "img-private",
            "inspect",
        ),
        (
            {
                "id": "crop-owner",
                "name": "image_crop",
                "arguments": {"media_ref": "img-private", "region": "label"},
            },
            {
                "owner_scope": {"expected_owner_id": "operator-a"},
                "crops": {
                    "img-private#label": {
                        "owner_id": "operator-b",
                        "privilege": "inspect",
                        "text": "private label",
                    }
                },
            },
            "retrieved_crop",
            "img-private#label",
            "inspect",
        ),
    ],
)
def test_agentic_tool_runtime_fails_closed_for_owner_scope_mismatch(
    tool_call: dict[str, object],
    fixture_context: dict[str, object],
    expected_source_type: str,
    expected_source_id: str,
    expected_privilege: str,
) -> None:
    run = execute_agentic_tool_calls([tool_call], fixture_context=fixture_context)

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "owner_scope_mismatch"
    assert observation["payload"]["source_type"] == expected_source_type
    assert observation["payload"]["source_id"] == expected_source_id
    assert observation["payload"]["owner_scope_checked"] is True
    assert observation["payload"]["expected_owner_id"] == "operator-a"
    assert observation["payload"]["actual_owner_id"] == "operator-b"
    assert observation["payload"]["privilege"] == expected_privilege
    assert "cross-owner" in observation["payload"]["corrective_action"]
    assert run.metrics["agentic_tool.failed_count"] == 1.0


def test_agentic_tool_runtime_allows_matching_owner_scope_payloads() -> None:
    run = execute_agentic_tool_calls(
        [
            {"id": "text-owner-ok", "name": "text_search", "arguments": {"query": "melix"}},
            {"id": "visit-owner-ok", "name": "visit", "arguments": {"url": "fixture://owned-page"}},
            {"id": "layout-owner-ok", "name": "layout_parse", "arguments": {"media_ref": "img-owned"}},
        ],
        fixture_context={
            "owner_scope": {"expected_owner_id": "operator-a", "privilege": "read"},
            "text_corpus": [
                {
                    "id": "doc-owned",
                    "owner_id": "operator-a",
                    "text": "Melix owned note.",
                }
            ],
            "pages": {
                "fixture://owned-page": {
                    "owner_id": "operator-a",
                    "title": "Owned Page",
                    "text": "Owned page.",
                }
            },
            "layouts": {
                "img-owned": {
                    "owner_id": "operator-a",
                    "elements": [{"kind": "text", "text": "owned"}],
                }
            },
        },
    )

    assert [observation["status"] for observation in run.observations] == [
        "completed",
        "completed",
        "completed",
    ]
    assert run.observations[0]["payload"]["results"][0]["id"] == "doc-owned"
    assert run.observations[1]["payload"]["text"] == "Owned page."
    assert run.observations[2]["payload"]["elements"][0]["text"] == "owned"


def test_agentic_tool_runtime_ignores_non_object_owner_scope_for_compatibility() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "visit-owner-compat", "name": "visit", "arguments": {"url": "fixture://legacy-page"}}],
        fixture_context={
            "owner_scope": "legacy fixture",
            "pages": {
                "fixture://legacy-page": {
                    "owner_id": "operator-b",
                    "title": "Legacy Page",
                    "text": "Legacy fixture page.",
                }
            },
        },
    )

    observation = run.observations[0]
    assert observation["status"] == "completed"
    assert observation["payload"]["text"] == "Legacy fixture page."


def test_agentic_tool_runtime_fails_closed_when_owner_scope_metadata_is_missing() -> None:
    run = execute_agentic_tool_calls(
        [{"id": "text-owner-missing", "name": "text_search", "arguments": {"query": "melix"}}],
        fixture_context={
            "owner_scope": {"expected_owner_id": "operator-a", "privilege": "read"},
            "text_corpus": [{"id": "doc-without-owner", "text": "Melix private note."}],
        },
    )

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "owner_scope_mismatch"
    assert observation["payload"]["source_type"] == "retrieved_document"
    assert observation["payload"]["source_id"] == "doc-without-owner"
    assert observation["payload"]["expected_owner_id"] == "operator-a"
    assert observation["payload"]["actual_owner_id"] == ""
    assert observation["payload"]["owner_scope_checked"] is True
    assert observation["payload"]["privilege"] == "read"


def test_agentic_tool_runtime_visit_reads_workspace_local_file_with_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note_path = workspace / "notes.md"
    note_path.write_text("# Melix\n\nWorkspace note.\n", encoding="utf-8")

    run = execute_agentic_tool_calls(
        [{"id": "visit-local", "name": "visit", "arguments": {"url": note_path.as_uri()}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "completed"
    assert observation["payload"]["url"] == note_path.as_uri()
    assert observation["payload"]["title"] == "notes.md"
    assert observation["payload"]["text"] == "# Melix\n\nWorkspace note.\n"
    assert observation["payload"]["found"] is True
    assert observation["payload"]["workspace_path_receipt"] == {
        "operation": "read",
        "workspace_root": str(workspace.resolve()),
        "requested_path": str(note_path),
        "resolved_path": str(note_path.resolve()),
        "allowed": True,
        "refusal_reason": "",
    }


def test_agentic_tool_runtime_visit_reads_percent_encoded_workspace_file_uri(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note_path = workspace / "space note.md"
    note_path.write_text("encoded uri note\n", encoding="utf-8")

    run = execute_agentic_tool_calls(
        [{"id": "visit-encoded-local", "name": "visit", "arguments": {"url": note_path.as_uri()}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "completed"
    assert observation["payload"]["text"] == "encoded uri note\n"
    assert observation["payload"]["workspace_path_receipt"]["requested_path"] == str(note_path)


@pytest.mark.parametrize(
    ("requested_path", "expected_reason"),
    [
        ("../outside/secret.md", "path_escapes_workspace"),
        ("config/.env", "sensitive_path"),
    ],
)
def test_agentic_tool_runtime_visit_refuses_workspace_path_before_reading(
    tmp_path: Path,
    requested_path: str,
    expected_reason: str,
) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("outside secret\n", encoding="utf-8")
    (workspace / "config").mkdir()
    (workspace / "config" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    run = execute_agentic_tool_calls(
        [{"id": "visit-blocked", "name": "visit", "arguments": {"url": requested_path}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "workspace_path_refused"
    assert observation["payload"]["source_type"] == "workspace_file"
    assert observation["payload"]["source_id"] == requested_path
    assert observation["payload"]["workspace_path_receipt"]["allowed"] is False
    assert observation["payload"]["workspace_path_receipt"]["refusal_reason"] == expected_reason
    assert "Workspace path resolver" in observation["payload"]["corrective_action"]


def test_agentic_tool_runtime_visit_reports_missing_workspace_file_with_receipt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    run = execute_agentic_tool_calls(
        [{"id": "visit-missing", "name": "visit", "arguments": {"url": "missing.md"}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "completed"
    assert observation["payload"]["found"] is False
    assert observation["payload"]["title"] == "missing.md"
    assert observation["payload"]["workspace_path_receipt"]["allowed"] is True
    assert observation["payload"]["workspace_path_receipt"]["resolved_path"] == str(
        workspace.resolve() / "missing.md"
    )


def test_agentic_tool_runtime_visit_reports_workspace_file_unavailable_with_receipt(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes-dir").mkdir()

    run = execute_agentic_tool_calls(
        [{"id": "visit-dir", "name": "visit", "arguments": {"url": "notes-dir"}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "workspace_file_unavailable"
    assert observation["payload"]["source_type"] == "workspace_file"
    assert observation["payload"]["source_id"] == "notes-dir"
    assert observation["payload"]["workspace_path_receipt"]["allowed"] is True
    assert observation["payload"]["workspace_path_receipt"]["resolved_path"] == str(
        (workspace / "notes-dir").resolve()
    )


def test_agentic_tool_runtime_visit_reports_non_utf8_workspace_file_unavailable(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    binary_path = workspace / "binary.bin"
    binary_path.write_bytes(b"\xff\xfe\x00")

    run = execute_agentic_tool_calls(
        [{"id": "visit-binary", "name": "visit", "arguments": {"url": "binary.bin"}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "failed"
    assert observation["payload"]["reason"] == "workspace_file_unavailable"
    assert observation["payload"]["source_type"] == "workspace_file"
    assert observation["payload"]["source_id"] == "binary.bin"
    assert observation["payload"]["workspace_path_receipt"]["allowed"] is True
    assert observation["payload"]["workspace_path_receipt"]["resolved_path"] == str(binary_path.resolve())


def test_agentic_tool_runtime_visit_ignores_remote_file_uri_for_workspace_reads(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    remote_url = "file://remote-host/private/note.md"

    run = execute_agentic_tool_calls(
        [{"id": "visit-remote-file", "name": "visit", "arguments": {"url": remote_url}}],
        fixture_context={"workspace_root": str(workspace)},
    )

    observation = run.observations[0]
    assert observation["status"] == "completed"
    assert observation["payload"] == {"url": remote_url, "text": "", "found": False}
