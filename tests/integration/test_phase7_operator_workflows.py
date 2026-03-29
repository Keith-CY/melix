from __future__ import annotations

import base64
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

from tests.integration.helpers import LiveMelixStack, abort_worker_request, read_metrics_export


def _post_json(url: str, payload: dict[str, object], *, timeout: float = 15.0) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read()
            if "application/json" in content_type:
                return response.status, json.loads(body.decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as error:
        body = error.read()
        content_type = error.headers.get("content-type", "")
        if "application/json" in content_type:
            return error.code, json.loads(body.decode("utf-8"))
        return error.code, body


def _abort_with_retry(socket_path: Path, request_id: str, *, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if abort_worker_request(socket_path, request_id):
            return True
        time.sleep(0.02)
    return False


def test_phase7_operator_smoke_records_image_metrics_and_text_interference() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={"MELIX_DETERMINISTIC_IMAGE_DELAY_MS": "120"},
    )
    try:
        stack.start()
        leader_result: dict[str, object] = {}

        def run_leader_image_job() -> None:
            status, payload = _post_json(
                stack.image_generations_url(),
                {
                    "id": "phase7-image-leader",
                    "model": "melix-dev-image",
                    "prompt": "operator smoke leader",
                    "size": "256x256",
                    "n": 3,
                    "response_format": "png",
                    "artifact_namespace": "phase7-smoke",
                },
                timeout=20.0,
            )
            leader_result["status"] = status
            leader_result["payload"] = payload

        queued_result: dict[str, object] = {}

        def run_queued_image_job() -> None:
            status, payload = _post_json(
                stack.image_generations_url(),
                {
                    "id": "phase7-image-queued",
                    "model": "melix-dev-image",
                    "prompt": "queued image smoke",
                    "size": "256x256",
                    "n": 1,
                    "response_format": "png",
                    "artifact_namespace": "phase7-smoke",
                },
                timeout=20.0,
            )
            queued_result["status"] = status
            queued_result["payload"] = payload

        leader = threading.Thread(target=run_leader_image_job, daemon=True)
        leader.start()
        time.sleep(0.05)
        queued = threading.Thread(target=run_queued_image_job, daemon=True)
        queued.start()
        time.sleep(0.05)

        chat_status, chat_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "measure text under image load"}],
            },
        )

        leader.join(timeout=20)
        queued.join(timeout=20)
        assert not leader.is_alive()
        assert not queued.is_alive()
        queue_metrics = read_metrics_export(stack.control_plane_metrics_path)

        edit_status, edit_payload = _post_json(
            stack.image_edits_url(),
            {
                "id": "phase7-image-edit",
                "model": "melix-dev-image",
                "prompt": "operator smoke edit",
                "image_base64": base64.b64encode(b"SOURCE").decode("ascii"),
                "mask_base64": base64.b64encode(b"MASK").decode("ascii"),
                "size": "256x256",
                "strength": 0.5,
                "response_format": "png",
                "n": 1,
            },
            timeout=20.0,
        )

        assert leader_result["status"] == 200
        assert chat_status == 200
        assert b"Echo" in chat_payload
        assert queued_result["status"] == 200
        assert edit_status == 200
        queued_payload = queued_result["payload"]
        assert queued_payload["job"]["job_id"] == "phase7-image-queued::image-generate"
        assert queued_payload["data"][0]["artifact"]["job_id"] == "phase7-image-queued::image-generate"
        assert edit_payload["job"]["job_id"] == "phase7-image-edit::image-edit"
        assert len(edit_payload["job"]["artifacts"]) == 3

        metrics = read_metrics_export(stack.control_plane_metrics_path)
        values = metrics["values"]
        queue_values = queue_metrics["values"]
        assert values["images.request_latency_ms"] >= 0
        assert values["images.job_latency_ms"] > 0
        assert values["images.artifact_publish_ms"] >= 0
        assert values["images.peak_memory_bytes"] > 0
        assert values["images.output_bytes"] > 0
        assert queue_values["images.queue_wait_ms"] > 0
        assert queue_values["scheduler.text_ttft_under_image_load_ms"] >= 0
    finally:
        stack.stop()


def test_phase7_image_cancel_smoke_returns_cancelled_conflict() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={"MELIX_DETERMINISTIC_IMAGE_DELAY_MS": "250"},
    )
    try:
        stack.start()
        result: dict[str, object] = {}

        def run_cancel_target() -> None:
            status, payload = _post_json(
                stack.image_generations_url(),
                {
                    "id": "phase7-image-cancel",
                    "model": "melix-dev-image",
                    "prompt": "cancel this image job",
                    "size": "256x256",
                    "n": 3,
                    "response_format": "png",
                },
                timeout=20.0,
            )
            result["status"] = status
            result["payload"] = payload

        worker = threading.Thread(target=run_cancel_target, daemon=True)
        worker.start()
        time.sleep(0.05)

        assert _abort_with_retry(stack.python_socket_path, "phase7-image-cancel") is True

        worker.join(timeout=20)
        assert not worker.is_alive()
        assert result["status"] == 409
        payload = result["payload"]
        assert payload["error"]["code"] == "cancelled"
        assert payload["error"]["message"]
    finally:
        stack.stop()
