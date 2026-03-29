from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, abort_worker_request, read_metrics_export


def timed_request(url: str, payload: dict[str, object], *, timeout: float = 20.0) -> tuple[float, int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            content_type = response.headers.get("content-type", "")
            body = response.read()
            if "application/json" in content_type:
                return elapsed_ms, response.status, json.loads(body.decode("utf-8"))
            return elapsed_ms, response.status, body
    except urllib.error.HTTPError as error:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        content_type = error.headers.get("content-type", "")
        body = error.read()
        if "application/json" in content_type:
            return elapsed_ms, error.code, json.loads(body.decode("utf-8"))
        return elapsed_ms, error.code, body


def metric_value(snapshot: dict[str, object], key: str) -> float:
    values = snapshot.get("values", {})
    if not isinstance(values, dict):
        return 0.0
    value = values.get(key, 0.0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def abort_with_retry(socket_path: Path, request_id: str, *, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if abort_worker_request(socket_path, request_id):
            return True
        time.sleep(0.02)
    return False


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DETERMINISTIC_IMAGE_DELAY_MS": "120"},
    )
    try:
        stack.start()
        generate_ms, generate_status, generate_payload = timed_request(
            stack.image_generations_url(),
            {
                "id": "phase7-generate",
                "model": "melix-dev-image",
                "prompt": "phase7 generate smoke",
                "size": "256x256",
                "n": 1,
                "response_format": "png",
                "artifact_namespace": "phase7-metrics",
            },
        )
        if generate_status != 200:
            raise SystemExit(f"image generation smoke failed: {generate_payload}")
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        generate_job_latency = metric_value(metrics, "images.job_latency_ms")
        generate_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")
        generate_peak_memory = metric_value(metrics, "images.peak_memory_bytes")
        generate_output_bytes = metric_value(metrics, "images.output_bytes")

        edit_ms, edit_status, edit_payload = timed_request(
            stack.image_edits_url(),
            {
                "id": "phase7-edit",
                "model": "melix-dev-image",
                "prompt": "phase7 edit smoke",
                "image_base64": base64.b64encode(b"SOURCE").decode("ascii"),
                "mask_base64": base64.b64encode(b"MASK").decode("ascii"),
                "size": "256x256",
                "strength": 0.5,
                "response_format": "png",
                "n": 1,
            },
        )
        if edit_status != 200:
            raise SystemExit(f"image edit smoke failed: {edit_payload}")
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        edit_job_latency = metric_value(metrics, "images.job_latency_ms")
        edit_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")
        edit_peak_memory = metric_value(metrics, "images.peak_memory_bytes")

        leader_result: dict[str, object] = {}

        def run_leader() -> None:
            elapsed_ms, status, payload = timed_request(
                stack.image_generations_url(),
                {
                    "id": "phase7-queue-leader",
                    "model": "melix-dev-image",
                    "prompt": "phase7 queue leader",
                    "size": "256x256",
                    "n": 3,
                    "response_format": "png",
                },
            )
            leader_result["elapsed_ms"] = elapsed_ms
            leader_result["status"] = status
            leader_result["payload"] = payload

        queued_result: dict[str, object] = {}

        def run_queued() -> None:
            elapsed_ms, status, payload = timed_request(
                stack.image_generations_url(),
                {
                    "id": "phase7-queued",
                    "model": "melix-dev-image",
                    "prompt": "phase7 queued follower",
                    "size": "256x256",
                    "n": 1,
                    "response_format": "png",
                },
            )
            queued_result["elapsed_ms"] = elapsed_ms
            queued_result["status"] = status
            queued_result["payload"] = payload

        leader = threading.Thread(target=run_leader, daemon=True)
        leader.start()
        time.sleep(0.05)
        queued = threading.Thread(target=run_queued, daemon=True)
        queued.start()
        time.sleep(0.05)

        text_under_image_ms, text_under_image_status, text_under_image_payload = timed_request(
            stack.chat_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "measure text under image load"}],
            },
        )
        if text_under_image_status != 200 or b"Echo" not in text_under_image_payload:
            raise SystemExit("text-under-image smoke failed")
        leader.join(timeout=20)
        queued.join(timeout=20)
        if leader.is_alive():
            raise SystemExit("phase7 leader image request did not finish")
        if queued.is_alive():
            raise SystemExit("phase7 queued image request did not finish")
        if queued_result.get("status") != 200:
            raise SystemExit(f"queued image smoke failed: {queued_result}")

        metrics = read_metrics_export(stack.control_plane_metrics_path)
        queue_wait_ms = metric_value(metrics, "images.queue_wait_ms")
        text_ttft_under_image = metric_value(metrics, "scheduler.text_ttft_under_image_load_ms")

        cancel_result: dict[str, object] = {}

        def run_cancel_target() -> None:
            elapsed_ms, status, payload = timed_request(
                stack.image_generations_url(),
                {
                    "id": "phase7-cancel",
                    "model": "melix-dev-image",
                    "prompt": "cancel me",
                    "size": "256x256",
                    "n": 3,
                    "response_format": "png",
                },
            )
            cancel_result["elapsed_ms"] = elapsed_ms
            cancel_result["status"] = status
            cancel_result["payload"] = payload

        cancel_thread = threading.Thread(target=run_cancel_target, daemon=True)
        cancel_thread.start()
        time.sleep(0.05)
        cancel_started_at = time.perf_counter()
        cancel_success = abort_with_retry(stack.python_socket_path, "phase7-cancel")
        cancel_request_ms = (time.perf_counter() - cancel_started_at) * 1000.0
        cancel_thread.join(timeout=20)
        if cancel_thread.is_alive():
            raise SystemExit("phase7 cancel target did not finish")
        if cancel_result.get("status") != 409:
            raise SystemExit(f"phase7 cancel smoke failed: {cancel_result}")

        print(
            "image_generate "
            f"request_latency_ms={generate_ms:.2f} "
            f"job_latency_ms={generate_job_latency:.2f} "
            f"artifact_publish_ms={generate_artifact_publish:.2f} "
            f"peak_memory_bytes={generate_peak_memory:.0f} "
            f"output_bytes={generate_output_bytes:.0f}"
        )
        print(
            "image_edit "
            f"request_latency_ms={edit_ms:.2f} "
            f"job_latency_ms={edit_job_latency:.2f} "
            f"artifact_publish_ms={edit_artifact_publish:.2f} "
            f"peak_memory_bytes={edit_peak_memory:.0f}"
        )
        print(
            "image_queue "
            f"request_latency_ms={float(queued_result['elapsed_ms']):.2f} "
            f"queue_wait_ms={queue_wait_ms:.2f}"
        )
        print(
            "text_under_image "
            f"request_latency_ms={text_under_image_ms:.2f} "
            f"scheduler_text_ttft_ms={text_ttft_under_image:.2f}"
        )
        print(
            "image_cancel "
            f"abort_request_ms={cancel_request_ms:.2f} "
            f"cancel_success={1 if cancel_success else 0} "
            f"response_status={cancel_result['status']}"
        )
    finally:
        stack.stop()


if __name__ == "__main__":
    main()
