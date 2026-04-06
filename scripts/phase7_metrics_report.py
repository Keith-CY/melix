from __future__ import annotations

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


def require_mapping(payload: object, context: str) -> dict[str, object]:
    if isinstance(payload, dict):
        return payload
    raise SystemExit(f"{context} did not return a JSON object payload")


def generated_artifact(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise SystemExit("image response did not include generated artifacts")
    first = data[0]
    if not isinstance(first, dict):
        raise SystemExit("image response datum was not an object")
    artifact = first.get("artifact")
    if isinstance(artifact, dict):
        return artifact
    raise SystemExit("image response datum did not include artifact metadata")


def rebuild_redo_edit_payload(job: dict[str, object], *, request_id: str) -> dict[str, object]:
    recipe = job.get("recipe")
    if not isinstance(recipe, dict):
        raise SystemExit("image job payload did not include a redo-capable recipe")
    payload: dict[str, object] = {
        "id": request_id,
        "model": job.get("model_id", ""),
        "prompt": recipe.get("prompt", ""),
        "size": recipe.get("size", "1024x1024"),
        "n": recipe.get("variant_count", 1),
        "response_format": recipe.get("response_format", "png"),
    }
    strength = recipe.get("strength")
    if isinstance(strength, (int, float)) and strength > 0:
        payload["strength"] = strength
    edit_mode = job.get("edit_mode")
    if isinstance(edit_mode, str) and edit_mode:
        payload["edit_mode"] = edit_mode
    source_artifact_id = job.get("source_artifact_id")
    if isinstance(source_artifact_id, str) and source_artifact_id:
        payload["source_artifact_id"] = source_artifact_id
    prompt_delta = job.get("prompt_delta")
    if isinstance(prompt_delta, str) and prompt_delta:
        payload["prompt_delta"] = prompt_delta
    return payload


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DETERMINISTIC_IMAGE_DELAY_MS": "120"},
    )
    try:
        stack.start()
        stack.wait_for_models(["melix-dev-image"])
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
        generate_payload = require_mapping(generate_payload, "image generation smoke")
        generate_job = require_mapping(generate_payload.get("job"), "image generation job payload")
        generate_artifact = generated_artifact(generate_payload)
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        generate_job_latency = metric_value(metrics, "images.job_latency_ms")
        generate_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")
        generate_peak_memory = metric_value(metrics, "images.peak_memory_bytes")
        generate_output_bytes = metric_value(metrics, "images.output_bytes")

        variation_ms, variation_status, variation_payload = timed_request(
            stack.image_edits_url(),
            {
                "id": "phase7-variation",
                "model": "melix-dev-image",
                "prompt": "phase7 variation smoke",
                "source_artifact_id": generate_artifact["artifact_id"],
                "edit_mode": "variation",
                "size": "256x256",
                "strength": 0.65,
                "response_format": "png",
                "n": 1,
            },
        )
        if variation_status != 200:
            raise SystemExit(f"image variation smoke failed: {variation_payload}")
        variation_payload = require_mapping(variation_payload, "image variation smoke")
        variation_job = require_mapping(variation_payload.get("job"), "image variation job payload")
        variation_artifact = generated_artifact(variation_payload)
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        variation_job_latency = metric_value(metrics, "images.job_latency_ms")
        variation_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")

        iterate_ms, iterate_status, iterate_payload = timed_request(
            stack.image_edits_url(),
            {
                "id": "phase7-iterate",
                "model": "melix-dev-image",
                "prompt": "",
                "source_artifact_id": variation_artifact["artifact_id"],
                "prompt_delta": "make the colors warmer",
                "edit_mode": "iterate",
                "size": "256x256",
                "strength": 0.65,
                "response_format": "png",
                "n": 1,
            },
        )
        if iterate_status != 200:
            raise SystemExit(f"image iterate smoke failed: {iterate_payload}")
        iterate_payload = require_mapping(iterate_payload, "image iterate smoke")
        iterate_job = require_mapping(iterate_payload.get("job"), "image iterate job payload")
        iterate_artifact = generated_artifact(iterate_payload)
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        iterate_job_latency = metric_value(metrics, "images.job_latency_ms")
        iterate_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")

        redo_ms, redo_status, redo_payload = timed_request(
            stack.image_edits_url(),
            rebuild_redo_edit_payload(iterate_job, request_id="phase7-redo"),
        )
        if redo_status != 200:
            raise SystemExit(f"image redo smoke failed: {redo_payload}")
        redo_payload = require_mapping(redo_payload, "image redo smoke")
        redo_job = require_mapping(redo_payload.get("job"), "image redo job payload")
        redo_artifact = generated_artifact(redo_payload)
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        redo_job_latency = metric_value(metrics, "images.job_latency_ms")
        redo_artifact_publish = metric_value(metrics, "images.artifact_publish_ms")

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

        timeout_stack = LiveMelixStack(
            repo_root,
            environment_overrides={
                "MELIX_DETERMINISTIC_IMAGE_DELAY_MS": "1500",
                "MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS": "1",
            },
        )
        try:
            timeout_stack.start()
            timeout_stack.wait_for_models(["melix-dev-image"])
            timeout_ms, timeout_status, timeout_payload = timed_request(
                timeout_stack.image_generations_url(),
                {
                    "id": "phase7-timeout",
                    "model": "melix-dev-image",
                    "prompt": "phase7 timeout smoke",
                    "size": "256x256",
                    "n": 1,
                    "response_format": "png",
                },
            )
            if timeout_status != 504:
                raise SystemExit(f"phase7 timeout smoke failed: {timeout_payload}")
            timeout_payload = require_mapping(timeout_payload, "image timeout smoke")
        finally:
            timeout_stack.stop()

        print(
            "image_generate "
            f"request_latency_ms={generate_ms:.2f} "
            f"job_latency_ms={generate_job_latency:.2f} "
            f"artifact_publish_ms={generate_artifact_publish:.2f} "
            f"peak_memory_bytes={generate_peak_memory:.0f} "
            f"output_bytes={generate_output_bytes:.0f} "
            f"artifact_id={generate_artifact['artifact_id']} "
            f"timeout_seconds={generate_job.get('request_timeout_seconds', 0)}"
        )
        print(
            "image_variation "
            f"request_latency_ms={variation_ms:.2f} "
            f"job_latency_ms={variation_job_latency:.2f} "
            f"artifact_publish_ms={variation_artifact_publish:.2f} "
            f"source_artifact_id={variation_job.get('source_artifact_id', '')} "
            f"parent_artifact_id={variation_artifact.get('parent_artifact_id', '')}"
        )
        print(
            "image_iterate "
            f"request_latency_ms={iterate_ms:.2f} "
            f"job_latency_ms={iterate_job_latency:.2f} "
            f"artifact_publish_ms={iterate_artifact_publish:.2f} "
            f"source_artifact_id={iterate_job.get('source_artifact_id', '')} "
            f"source_job_id={iterate_job.get('source_job_id', '')} "
            f"parent_artifact_id={iterate_artifact.get('parent_artifact_id', '')} "
            f"prompt_delta={iterate_job.get('prompt_delta', '')}"
        )
        print(
            "image_redo "
            f"request_latency_ms={redo_ms:.2f} "
            f"job_latency_ms={redo_job_latency:.2f} "
            f"artifact_publish_ms={redo_artifact_publish:.2f} "
            f"source_artifact_id={redo_job.get('source_artifact_id', '')} "
            f"parent_artifact_id={redo_artifact.get('parent_artifact_id', '')} "
            f"edit_mode={redo_job.get('edit_mode', '')}"
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
        print(
            "image_timeout "
            f"request_latency_ms={timeout_ms:.2f} "
            f"response_status={timeout_status} "
            f"error_code={timeout_payload['error']['code']} "
            f"timeout_seconds=1"
        )
    finally:
        stack.stop()


if __name__ == "__main__":
    main()
