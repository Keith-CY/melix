#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


REPO_ROOT = Path(
    os.environ.get("MELIX_BACKEND_IDENTITY_PROBE_REPO_ROOT", Path(__file__).resolve().parents[1])
).resolve()
CONTROL_PLANE_PROBE_PREFIX = "MELIX_BACKEND_IDENTITY_PROBE_JSON="
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2  # noqa: E402
from worker.model_registry.catalog import WorkerModelCatalog  # noqa: E402
from worker.registry import WorkerRegistry  # noqa: E402
from worker.runtime.mlx_text_runtime import MLXTextRuntime  # noqa: E402


class _PassiveTextBackend:
    runtime_name = "backend-identity-probe"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1_024


def _identity(model_id: str, adapter_id: str, generation: int):
    identity_type = getattr(common_pb2, "BackendModelIdentity", None)
    if identity_type is None:
        return object()
    return identity_type(
        requested_model_id=model_id,
        requested_adapter_id=adapter_id,
        route_generation=generation,
        worker_instance_id="worker-text-001",
    )


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _empty_control_plane_metrics() -> dict[str, float]:
    return {
        "control_plane_probe_available": 0.0,
        "control_plane_boundary_latency_ms_mean": 0.0,
        "control_plane_boundary_latency_ms_p95": 0.0,
        "retry_allowed_count": 0.0,
        "retry_suppressed_count": 0.0,
        "retry_exhausted_count": 0.0,
        "recovery_coalesced_caller_count": 0.0,
        "fresh_binding_count": 0.0,
        "duplicate_completed_tool_count": 0.0,
    }


def _parse_control_plane_probe_output(output: str) -> dict[str, float]:
    payloads = [
        line.removeprefix(CONTROL_PLANE_PROBE_PREFIX)
        for line in output.splitlines()
        if line.startswith(CONTROL_PLANE_PROBE_PREFIX)
    ]
    if not payloads:
        raise RuntimeError(
            "backend-identity Swift probe passed without emitting its JSON payload"
        )
    try:
        raw = json.loads(payloads[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("backend-identity Swift probe emitted invalid JSON") from exc
    expected = set(_empty_control_plane_metrics())
    if missing := expected - raw.keys():
        raise RuntimeError(
            "backend-identity Swift probe omitted metrics: " + ", ".join(sorted(missing))
        )
    return {key: float(raw[key]) for key in expected}


def _run_control_plane_probe() -> dict[str, float]:
    metrics = _empty_control_plane_metrics()
    if os.environ.get("MELIX_BACKEND_IDENTITY_PROBE_RUN_CONTROL") != "1":
        return metrics

    test_source = (
        REPO_ROOT
        / "services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift"
    )
    if not test_source.exists() or CONTROL_PLANE_PROBE_PREFIX not in test_source.read_text():
        return metrics

    env = os.environ.copy()
    env["MELIX_BACKEND_IDENTITY_PROBE"] = "1"
    env["HOME"] = os.fspath(
        REPO_ROOT / ".swift-home" / "backend-model-identity-probe"
    )
    env["CLANG_MODULE_CACHE_PATH"] = os.fspath(
        REPO_ROOT / ".build" / "ModuleCache.noindex" / "backend-model-identity-probe"
    )
    command = [
        "swift",
        "test",
        "--package-path",
        os.fspath(REPO_ROOT / "services/control-plane-swift"),
        "--filter",
        (
            "RequestCoordinatorTests/"
            "backendIdentityRecoveryProbeEmitsMeasuredControlPlaneEvidence()"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Swift CLI was not found for the control-plane probe") from exc
    output = completed.stdout or ""
    if completed.returncode != 0:
        raise RuntimeError(
            "backend-identity Swift probe failed with exit code "
            f"{completed.returncode}\n{output}"
        )
    return _parse_control_plane_probe_output(output)


def main() -> int:
    iterations = max(1, int(os.environ.get("MELIX_BACKEND_IDENTITY_PROBE_ITERATIONS", "20000")))
    sample_count = max(1, int(os.environ.get("MELIX_BACKEND_IDENTITY_PROBE_SAMPLES", "7")))
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=_PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    model = WorkerModelCatalog.dev_text_model()
    model.ext["melix.adapter_set_hash"] = "adapter-alpha"
    matched = _identity(model.model_id, "adapter-alpha", 7)
    mismatched = _identity("wrong-model", "wrong-adapter", 6)
    identity_guard = getattr(registry, "validate_backend_identity", None)
    if identity_guard is None:
        loaded = registry.load_model(model)
    else:
        loaded = registry.load_model(model, backend_identity=matched)

    matched_samples: list[float] = []
    mismatched_samples: list[float] = []
    output_before_mismatch_count = 0
    for _ in range(sample_count):
        started = time.perf_counter()
        for _ in range(iterations):
            error = (
                identity_guard(loaded.handle, matched)
                if identity_guard is not None
                else None if registry.get_loaded_model(loaded.handle) is not None else object()
            )
            if error is not None:
                raise AssertionError("matched backend identity was rejected")
        matched_samples.append((time.perf_counter() - started) * 1000.0 / iterations)

        started = time.perf_counter()
        for _ in range(iterations):
            error = identity_guard(loaded.handle, mismatched) if identity_guard is not None else None
            if identity_guard is not None and (
                error is None or error.code != "model_identity_mismatch"
            ):
                raise AssertionError("mismatched backend identity was accepted")
            if output_before_mismatch_count != 0:
                raise AssertionError("identity mismatch emitted output")
        mismatched_samples.append((time.perf_counter() - started) * 1000.0 / iterations)

    stats = registry.runtime_stats()
    observed_mismatch_count = float(getattr(stats, "model_identity_mismatch_count", 0))
    expected_mismatch_count = iterations * sample_count if identity_guard is not None else 0
    if observed_mismatch_count != expected_mismatch_count:
        raise AssertionError("identity mismatch diagnostics drifted during probe")

    metrics = {
        "iteration_count": float(iterations),
        "matched_boundary_latency_ms_mean": statistics.fmean(matched_samples),
        "matched_boundary_latency_ms_p95": _p95(matched_samples),
        "mismatch_count": observed_mismatch_count,
        "mismatched_boundary_latency_ms_mean": statistics.fmean(mismatched_samples),
        "mismatched_boundary_latency_ms_p95": _p95(mismatched_samples),
        "output_before_mismatch_count": float(output_before_mismatch_count),
        "sample_count": float(sample_count),
    }
    metrics.update(_run_control_plane_probe())
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
