from __future__ import annotations

import json
import tempfile
import time
import urllib.request
from typing import Any
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, get_cache_stats, read_metrics_export


def measure_cold_boot_to_ready(repo_root: Path) -> dict[str, float]:
    stack = LiveMelixStack(repo_root)
    started_at = time.perf_counter()
    try:
        stack.start()
        ready_ms = (time.perf_counter() - started_at) * 1_000.0
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


def wait_for_metrics(
    metrics_path: Path,
    keys: list[str],
    *,
    timeout_seconds: float = 60.0,
) -> dict[str, float]:
    deadline = time.perf_counter() + timeout_seconds
    last_values: dict[str, Any] = {}

    while time.perf_counter() < deadline:
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
        time.sleep(0.05)

    raise RuntimeError(
        f"Timed out waiting for control plane metrics {keys} in {metrics_path}: last={last_values}"
    )
