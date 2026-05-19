from __future__ import annotations

import json

import pytest

from worker.runtime.agentic_tools import AgenticToolRuntimeError, execute_agentic_tool_calls
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
            {"id": "tuple-1", "name": "text_search", "arguments": {"query": "alpha", "max_results": "bad"}},
            {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://text"}},
            {"id": "layout-1", "name": "layout_parse", "arguments": {"media_ref": "bad-layout"}},
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
            "text_corpus": {"default": [{"id": "doc-1", "text": "alpha beta"}]},
            "pages": {"fixture://text": "plain page"},
            "layouts": {"bad-layout": {"not": "a list"}},
            "crops": {"img-2": "raw crop text"},
        },
    )

    assert run.observations[0]["payload"]["result_count"] == 1
    assert run.observations[1]["payload"]["text"] == "plain page"
    assert run.observations[2]["payload"]["elements"] == []
    assert run.observations[3]["payload"]["purpose"] == "read label"
    assert run.observations[4]["payload"]["result"] == 4
    assert run.observations[5]["payload"]["result"] == 2
    assert run.observations[6]["status"] == "failed"


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
