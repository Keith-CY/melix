from __future__ import annotations

import json
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Callable
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)
from tests.integration.helpers import LiveMelixStack, get_cache_stats, read_metrics_export
from worker.model_registry.catalog import WorkerModelCatalog


def measure_cold_boot_to_ready(repo_root: Path) -> dict[str, float]:
    stack = LiveMelixStack(repo_root)
    started_at = time.perf_counter()
    try:
        stack.start()
        ready_ms = (time.perf_counter() - started_at) * 1_000.0
        swift_startup_metrics = wait_for_metrics(
            stack.swift_text_worker_metrics_path,
            [
                "swift_text.spawn_to_bootstrap_ms",
                "swift_text.registry_init_ms",
                "swift_text.services_init_ms",
                "swift_text.server_construct_ms",
                "swift_text.bootstrap_ms",
            ],
        )
        python_startup_metrics = wait_for_metrics(
            stack.python_worker_metrics_path,
            [
                "python_worker.spawn_to_bootstrap_ms",
                "python_worker.arg_parse_ms",
                "python_worker.registry_init_ms",
                "python_worker.server_build_ms",
                "python_worker.server_start_ms",
                "python_worker.bootstrap_ms",
            ],
        )
        bootstrap_metrics = wait_for_metrics(
            stack.control_plane_metrics_path,
            [
                "control_plane.http_ready_ms",
                "control_plane.background_preload_ms",
                "control_plane.background_preload_success",
            ],
        )
        first_text = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "warm the text model for product acceptance"}],
            },
        )
        if first_text["status"] != 200:
            raise SystemExit(f"first text warmup smoke failed: {first_text}")
        first_text_metrics = wait_for_metrics(
            stack.control_plane_metrics_path,
            [
                "control_plane.text_first_load_ms",
                "control_plane.text_first_load_estimated_resident_bytes",
                "control_plane.text_first_load_resident_bytes",
            ],
        )
        return {
            "cold_boot_to_ready_ms": round(ready_ms, 2),
            "swift_text_worker_ready_ms": round(
                float(stack.startup_timings.get("swift_text_worker_ready_ms", 0.0)), 2
            ),
            "python_worker_ready_ms": round(
                float(stack.startup_timings.get("python_worker_ready_ms", 0.0)), 2
            ),
            "control_plane_spawn_to_ready_ms": round(
                float(stack.startup_timings.get("control_plane_spawn_to_ready_ms", 0.0)), 2
            ),
            "swift_text_worker_spawn_to_bootstrap_ms": round(
                float(swift_startup_metrics["swift_text.spawn_to_bootstrap_ms"]), 2
            ),
            "swift_text_worker_registry_init_ms": round(
                float(swift_startup_metrics["swift_text.registry_init_ms"]), 2
            ),
            "swift_text_worker_services_init_ms": round(
                float(swift_startup_metrics["swift_text.services_init_ms"]), 2
            ),
            "swift_text_worker_server_construct_ms": round(
                float(swift_startup_metrics["swift_text.server_construct_ms"]), 2
            ),
            "swift_text_worker_bootstrap_ms": round(
                float(swift_startup_metrics["swift_text.bootstrap_ms"]), 2
            ),
            "python_worker_spawn_to_bootstrap_ms": round(
                float(python_startup_metrics["python_worker.spawn_to_bootstrap_ms"]), 2
            ),
            "python_worker_arg_parse_ms": round(
                float(python_startup_metrics["python_worker.arg_parse_ms"]), 2
            ),
            "python_worker_registry_init_ms": round(
                float(python_startup_metrics["python_worker.registry_init_ms"]), 2
            ),
            "python_worker_server_build_ms": round(
                float(python_startup_metrics["python_worker.server_build_ms"]), 2
            ),
            "python_worker_server_start_ms": round(
                float(python_startup_metrics["python_worker.server_start_ms"]), 2
            ),
            "python_worker_bootstrap_ms": round(
                float(python_startup_metrics["python_worker.bootstrap_ms"]), 2
            ),
            "http_ready_ms": round(
                float(bootstrap_metrics["control_plane.http_ready_ms"]), 2
            ),
            "background_preload_ms": round(
                float(bootstrap_metrics["control_plane.background_preload_ms"]), 2
            ),
            "background_preload_success": float(
                bootstrap_metrics["control_plane.background_preload_success"]
            ),
            "first_text_model_warm_ms": round(
                float(first_text_metrics["control_plane.text_first_load_ms"]), 2
            ),
            "text_model_load_estimated_resident_bytes": round(
                float(first_text_metrics["control_plane.text_first_load_estimated_resident_bytes"]), 2
            ),
            "text_model_load_resident_bytes": round(
                float(first_text_metrics["control_plane.text_first_load_resident_bytes"]), 2
            ),
        }
    finally:
        stack.stop()


def collect_restart_recovery_evidence(repo_root: Path) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="melix-phase8-recovery-") as cache_root_str:
        cache_root = Path(cache_root_str)

        first_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        snapshot_id = ""
        try:
            first_stack.start()
            initial = stream_chat_completion(
                first_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "messages": [{"role": "user", "content": "persist a release-gate recovery snapshot"}],
                    "save_boundary_snapshot": True,
                },
            )
            if initial["status"] != 200:
                raise SystemExit(f"initial recovery smoke failed: {initial}")
            cache_response = get_cache_stats(first_stack.swift_socket_path)
            snapshot_id = cache_response.snapshot.snapshots[-1].snapshot_id
            if not snapshot_id:
                raise SystemExit("recovery smoke did not produce a boundary snapshot")
        finally:
            first_stack.stop()

        second_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        started_at = time.perf_counter()
        try:
            second_stack.start()
            restart_to_ready_ms = (time.perf_counter() - started_at) * 1_000.0
            restore_started_at = time.perf_counter()
            restored = stream_chat_completion(
                second_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "restore_snapshot_id": snapshot_id,
                    "messages": [{"role": "user", "content": "resume after release-gate restart"}],
                },
            )
            restore_ms = (time.perf_counter() - restore_started_at) * 1_000.0
            recovery_ms = (time.perf_counter() - started_at) * 1_000.0
            success = restored["status"] == 200 and "data: [DONE]" in restored["body"]
            bootstrap_metrics = wait_for_metrics(
                second_stack.control_plane_metrics_path,
                [
                    "control_plane.http_ready_ms",
                    "control_plane.background_preload_ms",
                    "control_plane.background_preload_success",
                ],
            )
            return {
                "restart_to_ready_ms": round(restart_to_ready_ms, 2),
                "restart_swift_text_worker_ready_ms": round(
                    float(second_stack.startup_timings.get("swift_text_worker_ready_ms", 0.0)), 2
                ),
                "restart_python_worker_ready_ms": round(
                    float(second_stack.startup_timings.get("python_worker_ready_ms", 0.0)), 2
                ),
                "restart_control_plane_spawn_to_ready_ms": round(
                    float(second_stack.startup_timings.get("control_plane_spawn_to_ready_ms", 0.0)), 2
                ),
                "snapshot_restore_ms": round(restore_ms, 2),
                "restart_recovery_ms": round(recovery_ms, 2),
                "restart_recovery_success_rate": 100.0 if success else 0.0,
                "http_ready_ms": round(
                    float(bootstrap_metrics["control_plane.http_ready_ms"]), 2
                ),
                "background_preload_ms": round(
                    float(bootstrap_metrics["control_plane.background_preload_ms"]), 2
                ),
                "background_preload_success": float(
                    bootstrap_metrics["control_plane.background_preload_success"]
                ),
            }
        finally:
            second_stack.stop()


def collect_runtime_core_evidence(repo_root: Path) -> dict[str, Any]:
    multi_model = _collect_multi_model_coexistence_evidence(repo_root)
    memory_guard = _collect_prefill_memory_guard_evidence(repo_root)
    return {
        **multi_model,
        **memory_guard,
    }


def stream_chat_completion(stack: LiveMelixStack, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return {
            "status": response.status,
            "body": body,
        }


def wait_for_metric_minimum(
    metrics_path: Path,
    key: str,
    *,
    minimum: float,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 0.05,
    clock: Callable[[], float] = time.perf_counter,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> float:
    deadline = clock() + timeout_seconds
    last_value = 0.0

    while True:
        if metrics_path.exists():
            try:
                payload = read_metrics_export(metrics_path)
                values = payload.get("values", {})
                if isinstance(values, dict):
                    candidate = values.get(key, 0.0)
                    if isinstance(candidate, (int, float)):
                        last_value = float(candidate)
                        if last_value >= minimum:
                            return last_value
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        now = clock()
        if now >= deadline:
            break
        sleep_fn(min(poll_interval_seconds, max(0.0, deadline - now)))

    raise RuntimeError(
        f"Timed out waiting for metric {key} >= {minimum} in {metrics_path}: last={last_value}"
    )


def wait_for_metrics(
    metrics_path: Path,
    keys: list[str],
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 0.05,
    clock: Callable[[], float] = time.perf_counter,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, float]:
    deadline = clock() + timeout_seconds
    last_values: dict[str, Any] = {}

    while True:
        if metrics_path.exists():
            try:
                payload = read_metrics_export(metrics_path)
                values = payload.get("values", {})
                if isinstance(values, dict):
                    last_values = values
                    if all(key in values for key in keys):
                        return {key: float(values[key]) for key in keys}
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        now = clock()
        if now >= deadline:
            break
        sleep_fn(min(poll_interval_seconds, max(0.0, deadline - now)))

    raise RuntimeError(
        f"Timed out waiting for metrics {keys} in {metrics_path}: last={last_values}"
    )


def _collect_multi_model_coexistence_evidence(repo_root: Path) -> dict[str, Any]:
    required_models = ["melix-dev-text", "melix-dev-embed", "melix-dev-rerank"]
    stack = LiveMelixStack(repo_root)
    successful_requests = 0
    try:
        stack.start()

        text = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "warm the live text route"}],
            },
        )
        if text["status"] != 200 or "data: [DONE]" not in text["body"]:
            raise SystemExit(f"runtime-core text smoke failed: {text}")
        successful_requests += 1

        embedding_status, embedding_payload = _post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
            {
                "model": "melix-dev-embed",
                "input": ["alpha", "beta"],
            },
        )
        if embedding_status != 200 or not isinstance(embedding_payload, dict):
            raise SystemExit(
                f"runtime-core embedding smoke failed: status={embedding_status} payload={embedding_payload}"
            )
        successful_requests += 1

        rerank_status, rerank_payload = _post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/rerank",
            {
                "model": "melix-dev-rerank",
                "query": "swift worker",
                "documents": ["python bridge", "swift worker"],
                "top_k": 2,
            },
        )
        if rerank_status != 200 or not isinstance(rerank_payload, dict):
            raise SystemExit(
                f"runtime-core rerank smoke failed: status={rerank_status} payload={rerank_payload}"
            )
        successful_requests += 1

        stack.wait_for_models(required_models, timeout_seconds=30)
        model_states = _read_model_states(stack.models_url())
        ready_model_ids = [
            model_id for model_id in required_models if model_states.get(model_id) in {"warm", "pinned"}
        ]

        return {
            "multi_model_ready_count": len(ready_model_ids),
            "multi_model_request_success_rate": round(
                (successful_requests / len(required_models)) * 100.0,
                2,
            ),
            "multi_model_ready_model_ids": ready_model_ids,
        }
    finally:
        stack.stop()


def _collect_prefill_memory_guard_evidence(repo_root: Path) -> dict[str, Any]:
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={
            "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "16384",
            "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES": "16384",
        },
    )
    try:
        stack.start()
        response = _run_prefill_memory_guard_probe(stack)
        rejection_count = wait_for_metric_minimum(
            stack.swift_text_worker_metrics_path,
            "swift_text.prefill_memory_guard_rejection_count",
            minimum=1,
            timeout_seconds=10.0,
        )
        guard_metrics = wait_for_metrics(
            stack.swift_text_worker_metrics_path,
            [
                "swift_text.prefill_guard_last_prompt_tokens",
                "swift_text.prefill_guard_last_required_bytes",
                "swift_text.prefill_guard_last_budget_bytes",
            ],
        )

        success = (
            response["ok"] is False
            and response["error_code"] == "prefill_memory_guard_exceeded"
            and rejection_count >= 1
        )
        if not success:
            raise SystemExit(f"runtime-core prefill guard smoke failed: {response}")

        return {
            "prefill_memory_guard_rejection_count": round(rejection_count, 2),
            "prefill_memory_guard_success_rate": 100.0,
            "prefill_memory_guard_last_prompt_tokens": round(
                float(guard_metrics["swift_text.prefill_guard_last_prompt_tokens"]),
                2,
            ),
            "prefill_memory_guard_last_required_bytes": round(
                float(guard_metrics["swift_text.prefill_guard_last_required_bytes"]),
                2,
            ),
            "prefill_memory_guard_last_budget_bytes": round(
                float(guard_metrics["swift_text.prefill_guard_last_budget_bytes"]),
                2,
            ),
        }
    finally:
        stack.stop()


def _post_json(url: str, payload: dict[str, object]) -> tuple[int, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _read_model_states(models_url: str) -> dict[str, str]:
    with urllib.request.urlopen(models_url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {item["id"]: item["melix_state"] for item in payload["data"]}


def _run_prefill_memory_guard_probe(stack: LiveMelixStack) -> dict[str, Any]:
    channel = grpc.insecure_channel(f"unix://{stack.swift_socket_path}")
    try:
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        load_response = runtime_stub.LoadModel(
            runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
            timeout=5,
        )
        if not load_response.ok or not load_response.model_handle:
            return {
                "ok": False,
                "error_code": load_response.error.code or "load_failed",
                "error_message": load_response.error.message,
            }

        response = inference_stub.Prefill(
            inference_pb2.PrefillRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="phase8-runtime-core-prefill"),
                    model_handle=load_response.model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="alpha")],
                    )
                ],
                return_decode_handle=True,
                prefill_step_size=0,
            ),
            timeout=5,
        )
        return {
            "ok": response.ok,
            "error_code": response.error.code,
            "error_message": response.error.message,
        }
    finally:
        channel.close()
