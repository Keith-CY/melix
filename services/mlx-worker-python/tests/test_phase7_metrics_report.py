from __future__ import annotations

from pathlib import Path

import pytest

from scripts import phase7_metrics_report


class _FakeStack:
    def __init__(self, name: str) -> None:
        self.name = name
        self.control_plane_metrics_path = Path(f"/tmp/{name}-metrics.json")
        self.python_socket_path = Path(f"/tmp/{name}.sock")
        self.started = False
        self.stopped = False
        self.waited_models: list[list[str]] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def wait_for_models(self, model_ids: list[str]) -> None:
        self.waited_models.append(model_ids)

    def image_generations_url(self) -> str:
        return f"https://{self.name}/v1/images/generations"

    def image_edits_url(self) -> str:
        return f"https://{self.name}/v1/images/edits"

    def chat_url(self) -> str:
        return f"https://{self.name}/v1/chat/completions"


class _ImmediateThread:
    def __init__(self, *, target, daemon: bool) -> None:  # noqa: ANN001
        self._target = target
        self._alive = False

    def start(self) -> None:
        self._alive = True
        self._target()
        self._alive = False

    def join(self, timeout: float | None = None) -> None:  # noqa: ARG002
        return None

    def is_alive(self) -> bool:
        return self._alive


def _build_success_responses() -> list[tuple[float, int, object]]:
    return [
        (
            10.0,
            200,
            {
                "job": {
                    "job_id": "phase7-generate::image-generate",
                    "model_id": "melix-dev-image",
                    "request_timeout_seconds": 1800,
                    "recipe": {
                        "prompt": "phase7 generate smoke",
                        "size": "256x256",
                        "variant_count": 1,
                        "response_format": "png",
                        "artifact_namespace": "phase7-metrics",
                        "strength": 0.0,
                    },
                },
                "data": [{"artifact": {"artifact_id": "artifact-generate", "parent_artifact_id": ""}}],
            },
        ),
        (
            11.0,
            200,
            {
                "job": {
                    "job_id": "phase7-variation::image-edit",
                    "model_id": "melix-dev-image",
                    "source_artifact_id": "artifact-generate",
                    "source_job_id": "phase7-generate::image-generate",
                    "prompt_delta": "",
                    "edit_mode": "variation",
                    "recipe": {
                        "prompt": "phase7 variation smoke",
                        "size": "256x256",
                        "variant_count": 1,
                        "response_format": "png",
                        "strength": 0.65,
                    },
                },
                "data": [{"artifact": {"artifact_id": "artifact-variation", "parent_artifact_id": "artifact-generate"}}],
            },
        ),
        (
            12.0,
            200,
            {
                "job": {
                    "job_id": "phase7-iterate::image-edit",
                    "model_id": "melix-dev-image",
                    "source_artifact_id": "artifact-variation",
                    "source_job_id": "phase7-variation::image-edit",
                    "prompt_delta": "make the colors warmer",
                    "edit_mode": "iterate",
                    "recipe": {
                        "prompt": "make the colors warmer",
                        "size": "256x256",
                        "variant_count": 1,
                        "response_format": "png",
                        "strength": 0.65,
                    },
                },
                "data": [{"artifact": {"artifact_id": "artifact-iterate", "parent_artifact_id": "artifact-variation"}}],
            },
        ),
        (
            13.0,
            200,
            {
                "job": {
                    "job_id": "phase7-redo::image-edit",
                    "model_id": "melix-dev-image",
                    "source_artifact_id": "artifact-variation",
                    "source_job_id": "phase7-variation::image-edit",
                    "prompt_delta": "make the colors warmer",
                    "edit_mode": "iterate",
                    "recipe": {
                        "prompt": "make the colors warmer",
                        "size": "256x256",
                        "variant_count": 1,
                        "response_format": "png",
                        "strength": 0.65,
                    },
                },
                "data": [{"artifact": {"artifact_id": "artifact-redo", "parent_artifact_id": "artifact-variation"}}],
            },
        ),
        (14.0, 200, {"job": {"job_id": "leader"}}),
        (15.0, 200, {"job": {"job_id": "queued"}}),
        (16.0, 200, b"Echo"),
        (17.0, 409, {"error": {"code": "cancelled"}}),
        (18.0, 504, {"error": {"code": "deadline_exceeded"}}),
    ]


def _patch_main_dependencies(monkeypatch, responses: list[tuple[float, int, object]]) -> tuple[_FakeStack, _FakeStack]:
    primary_stack = _FakeStack("primary")
    timeout_stack = _FakeStack("timeout")
    stack_iter = iter([primary_stack, timeout_stack])
    monkeypatch.setattr(
        phase7_metrics_report,
        "LiveMelixStack",
        lambda repo_root, environment_overrides=None: next(stack_iter),
    )
    monkeypatch.setattr(phase7_metrics_report.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(phase7_metrics_report, "abort_with_retry", lambda *args, **kwargs: True)
    metrics_iter = iter(
        [
            {
                "values": {
                    "images.job_latency_ms": 48.0,
                    "images.artifact_publish_ms": 2.5,
                    "images.peak_memory_bytes": 65536.0,
                    "images.output_bytes": 2048.0,
                }
            },
            {"values": {"images.job_latency_ms": 52.0, "images.artifact_publish_ms": 3.0}},
            {"values": {"images.job_latency_ms": 57.0, "images.artifact_publish_ms": 3.5}},
            {"values": {"images.job_latency_ms": 59.0, "images.artifact_publish_ms": 4.0}},
            {
                "values": {
                    "images.queue_wait_ms": 7.0,
                    "scheduler.text_ttft_under_image_load_ms": 12.0,
                }
            },
        ]
    )
    monkeypatch.setattr(phase7_metrics_report, "read_metrics_export", lambda path: next(metrics_iter))
    response_iter = iter(responses)
    monkeypatch.setattr(
        phase7_metrics_report,
        "timed_request",
        lambda url, payload, timeout=20.0: next(response_iter),  # noqa: ARG005
    )
    return primary_stack, timeout_stack


def test_rebuild_redo_edit_payload_uses_recipe_and_lineage() -> None:
    payload = phase7_metrics_report.rebuild_redo_edit_payload(
        {
            "model_id": "melix-dev-image",
            "source_artifact_id": "artifact-source",
            "prompt_delta": "make the colors warmer",
            "edit_mode": "iterate",
            "recipe": {
                "prompt": "make the colors warmer",
                "size": "256x256",
                "variant_count": 2,
                "response_format": "png",
                "strength": 0.65,
            },
        },
        request_id="redo-request",
    )

    assert payload == {
        "id": "redo-request",
        "model": "melix-dev-image",
        "prompt": "make the colors warmer",
        "size": "256x256",
        "n": 2,
        "response_format": "png",
        "strength": 0.65,
        "edit_mode": "iterate",
        "source_artifact_id": "artifact-source",
        "prompt_delta": "make the colors warmer",
    }


def test_require_mapping_rejects_non_object_payload() -> None:
    with pytest.raises(SystemExit, match="did not return a JSON object payload"):
        phase7_metrics_report.require_mapping([], "variation smoke")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "image response did not include generated artifacts"),
        ({"data": [123]}, "image response datum was not an object"),
        ({"data": [{}]}, "image response datum did not include artifact metadata"),
    ],
)
def test_generated_artifact_rejects_invalid_payload_shapes(payload: dict[str, object], message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        phase7_metrics_report.generated_artifact(payload)


def test_rebuild_redo_edit_payload_requires_recipe() -> None:
    with pytest.raises(SystemExit, match="redo-capable recipe"):
        phase7_metrics_report.rebuild_redo_edit_payload({}, request_id="redo")


def test_phase7_metrics_report_main_emits_iteration_and_timeout_evidence(
    monkeypatch,
    capsys,
) -> None:
    primary_stack, timeout_stack = _patch_main_dependencies(monkeypatch, _build_success_responses())

    phase7_metrics_report.main()

    output = capsys.readouterr().out
    assert "image_generate " in output
    assert "image_variation " in output
    assert "image_iterate " in output
    assert "image_redo " in output
    assert "image_timeout " in output
    assert "source_artifact_id=artifact-variation" in output
    assert "error_code=deadline_exceeded" in output
    assert primary_stack.started is True
    assert primary_stack.stopped is True
    assert timeout_stack.started is True
    assert timeout_stack.stopped is True


@pytest.mark.parametrize(
    ("index", "response", "message"),
    [
        (1, (11.0, 500, {"error": {"code": "bad"}}), "image variation smoke failed"),
        (2, (12.0, 500, {"error": {"code": "bad"}}), "image iterate smoke failed"),
        (3, (13.0, 500, {"error": {"code": "bad"}}), "image redo smoke failed"),
        (8, (18.0, 200, {"ok": True}), "phase7 timeout smoke failed"),
    ],
)
def test_phase7_metrics_report_main_surfaces_iteration_failure_stages(
    monkeypatch,
    index: int,
    response: tuple[float, int, object],
    message: str,
) -> None:
    responses = _build_success_responses()
    responses[index] = response
    _patch_main_dependencies(monkeypatch, responses)

    with pytest.raises(SystemExit, match=message):
        phase7_metrics_report.main()
