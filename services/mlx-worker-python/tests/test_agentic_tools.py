from __future__ import annotations

import json

import pytest

from worker.runtime.agentic_tools import AgenticToolRuntimeError, execute_agentic_tool_calls


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
