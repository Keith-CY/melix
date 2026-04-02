from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.productization.release_gates import (
    _build_maintenance_core as _build_release_gate_maintenance_core,
    _ensure_training_dataset,
    _evaluate_section_metrics,
    load_release_gate_policy,
)


def collect_operator_action_evidence(jobs_root: str | Path) -> dict[str, Any]:
    root = Path(jobs_root)
    core = _build_maintenance_core(root)
    _seed_registry_state(core, root)

    started_at = time.perf_counter()
    events = list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(root / "registry-snapshot"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            )
        )
    )
    latency_ms = (time.perf_counter() - started_at) * 1_000.0
    manifest_json = next(
        event.manifest.manifest_json
        for event in events
        if event.HasField("manifest")
    )
    payload = json.loads(manifest_json)

    return {
        "operator_action_latency_ms": round(latency_ms, 2),
        "registry_job_count": len(payload["jobs"]),
        "registry_adapter_count": len(payload["adapters"]),
    }


def build_phase6_vision_metrics_report(
    *,
    ingress: dict[str, Any],
    ocr: dict[str, Any],
    vlm: dict[str, Any],
    metrics_snapshot: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "vision.ingress.local_image_success": bool(ingress.get("local_image_success")),
        "vision.ingress.remote_image_success": bool(ingress.get("remote_image_success")),
        "vision.ingress.multi_image_success": bool(ingress.get("multi_image_success")),
        "vision.ocr.default_stop_success": bool(ocr.get("default_stop_success")),
        "vision.vlm.tool_call_success": bool(vlm.get("tool_call_success")),
    }
    passed_checks = sum(1 for value in checks.values() if value)
    total_checks = len(checks)

    metrics = {
        "vision.integration_success_rate": _success_rate(passed_checks, total_checks),
        "vision.ingress.local_image_success_rate": _success_rate(
            int(checks["vision.ingress.local_image_success"]), 1
        ),
        "vision.ingress.remote_image_success_rate": _success_rate(
            int(checks["vision.ingress.remote_image_success"]), 1
        ),
        "vision.ingress.multi_image_success_rate": _success_rate(
            int(checks["vision.ingress.multi_image_success"]), 1
        ),
        "vision.ocr.default_stop_success_rate": _success_rate(
            int(checks["vision.ocr.default_stop_success"]), 1
        ),
        "vision.vlm.tool_call_success_rate": _success_rate(
            int(checks["vision.vlm.tool_call_success"]), 1
        ),
        "vision.ocr.request_latency_ms": _rounded_float(ocr.get("request_latency_ms")),
        "vision.vlm.request_latency_ms": _rounded_float(vlm.get("request_latency_ms")),
        "vision.ocr_latency_ms": _metric_value(metrics_snapshot, "vision.ocr_latency_ms"),
        "vision.vlm_first_token_ms": _metric_value(
            metrics_snapshot, "vision.vlm_first_token_ms"
        ),
        "vision.preprocess_latency_ms": _metric_value(
            metrics_snapshot, "vision.preprocess_latency_ms"
        ),
        "vision.preprocess_peak_memory_bytes": _metric_value(
            metrics_snapshot, "vision.preprocess_peak_memory_bytes"
        ),
        "vision.cache_memory_bytes": _metric_value(
            metrics_snapshot, "vision.cache_memory_bytes"
        ),
        "vision.cache_hit_rate": _metric_value(metrics_snapshot, "vision.cache_hit_rate"),
    }

    return {
        "checks": checks,
        "metrics": metrics,
        "ingress": ingress,
        "ocr": ocr,
        "vlm": vlm,
    }


def build_phase8_metrics_report(
    *,
    cold_boot_to_ready_ms: float | None = None,
    cold_boot: dict[str, Any] | None = None,
    operator: dict[str, Any],
    release_gate_report: dict[str, Any],
    runtime_core: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = policy or load_release_gate_policy()
    cold_boot_evidence = dict(cold_boot or {})
    if cold_boot_to_ready_ms is not None:
        cold_boot_evidence.setdefault("cold_boot_to_ready_ms", cold_boot_to_ready_ms)
    recovery = release_gate_report["recovery"]
    runtime_core_evidence = dict(runtime_core or release_gate_report.get("runtime_core", {}))
    cache_recovery_metrics = dict(
        release_gate_report.get("benchmarks", {}).get("recovery_metrics", {})
    )

    metrics = {
        "desktop.cold_boot_to_ready_ms": round(
            float(cold_boot_evidence["cold_boot_to_ready_ms"]), 2
        ),
        "desktop.swift_text_worker_ready_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_ready_ms", 0.0)), 2
        ),
        "desktop.python_worker_ready_ms": round(
            float(cold_boot_evidence.get("python_worker_ready_ms", 0.0)), 2
        ),
        "desktop.control_plane_spawn_to_ready_ms": round(
            float(cold_boot_evidence.get("control_plane_spawn_to_ready_ms", 0.0)), 2
        ),
        "desktop.swift_text_worker_spawn_to_bootstrap_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_spawn_to_bootstrap_ms", 0.0)), 2
        ),
        "desktop.swift_text_worker_registry_init_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_registry_init_ms", 0.0)), 2
        ),
        "desktop.swift_text_worker_services_init_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_services_init_ms", 0.0)), 2
        ),
        "desktop.swift_text_worker_server_construct_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_server_construct_ms", 0.0)), 2
        ),
        "desktop.swift_text_worker_bootstrap_ms": round(
            float(cold_boot_evidence.get("swift_text_worker_bootstrap_ms", 0.0)), 2
        ),
        "desktop.python_worker_spawn_to_bootstrap_ms": round(
            float(cold_boot_evidence.get("python_worker_spawn_to_bootstrap_ms", 0.0)), 2
        ),
        "desktop.python_worker_arg_parse_ms": round(
            float(cold_boot_evidence.get("python_worker_arg_parse_ms", 0.0)), 2
        ),
        "desktop.python_worker_registry_init_ms": round(
            float(cold_boot_evidence.get("python_worker_registry_init_ms", 0.0)), 2
        ),
        "desktop.python_worker_server_build_ms": round(
            float(cold_boot_evidence.get("python_worker_server_build_ms", 0.0)), 2
        ),
        "desktop.python_worker_server_start_ms": round(
            float(cold_boot_evidence.get("python_worker_server_start_ms", 0.0)), 2
        ),
        "desktop.python_worker_bootstrap_ms": round(
            float(cold_boot_evidence.get("python_worker_bootstrap_ms", 0.0)), 2
        ),
        "desktop.http_ready_ms": round(
            float(cold_boot_evidence.get("http_ready_ms", cold_boot_evidence["cold_boot_to_ready_ms"])), 2
        ),
        "desktop.background_preload_ms": round(
            float(cold_boot_evidence.get("background_preload_ms", 0.0)), 2
        ),
        "desktop.first_text_model_warm_ms": round(
            float(cold_boot_evidence.get("first_text_model_warm_ms", 0.0)), 2
        ),
        "desktop.text_model_load_estimated_resident_bytes": round(
            float(cold_boot_evidence.get("text_model_load_estimated_resident_bytes", 0.0)), 2
        ),
        "desktop.text_model_load_resident_bytes": round(
            float(cold_boot_evidence.get("text_model_load_resident_bytes", 0.0)), 2
        ),
        "desktop.operator_action_latency_ms": round(
            float(operator["operator_action_latency_ms"]), 2
        ),
        "desktop.restart_to_ready_ms": round(
            float(recovery.get("restart_to_ready_ms", recovery["restart_recovery_ms"])), 2
        ),
        "desktop.restart_swift_text_worker_ready_ms": round(
            float(recovery.get("restart_swift_text_worker_ready_ms", 0.0)), 2
        ),
        "desktop.restart_python_worker_ready_ms": round(
            float(recovery.get("restart_python_worker_ready_ms", 0.0)), 2
        ),
        "desktop.restart_control_plane_spawn_to_ready_ms": round(
            float(recovery.get("restart_control_plane_spawn_to_ready_ms", 0.0)), 2
        ),
        "desktop.snapshot_restore_ms": round(
            float(recovery.get("snapshot_restore_ms", 0.0)), 2
        ),
        "desktop.restart_recovery_ms": round(
            float(recovery["restart_recovery_ms"]), 2
        ),
        "desktop.crash_recovery_success_rate": float(
            recovery["restart_recovery_success_rate"]
        ),
        "runtime.multi_model_ready_count": round(
            float(runtime_core_evidence.get("multi_model_ready_count", 0.0)),
            2,
        ),
        "runtime.multi_model_request_success_rate": round(
            float(runtime_core_evidence.get("multi_model_request_success_rate", 0.0)),
            2,
        ),
        "runtime.prefill_memory_guard_rejection_count": round(
            float(runtime_core_evidence.get("prefill_memory_guard_rejection_count", 0.0)),
            2,
        ),
        "runtime.prefill_memory_guard_success_rate": round(
            float(runtime_core_evidence.get("prefill_memory_guard_success_rate", 0.0)),
            2,
        ),
        "release.benchmark_regression_pct": round(
            compute_benchmark_regression_pct(release_gate_report["benchmarks"], active_policy),
            2,
        ),
        "release.smoke_pass_rate": round(
            compute_release_smoke_pass_rate(release_gate_report, active_policy),
            2,
        ),
        "install.success_rate": round(
            compute_install_success_rate(release_gate_report["install"]),
            2,
        ),
        "training.job_duration_ms": round(
            float(release_gate_report["training"]["training_duration_ms"]),
            2,
        ),
        "training.adapter_publish_ms": round(
            float(release_gate_report["training"]["adapter_publish_ms"]),
            2,
        ),
        "cache_recovery.hot_followup_ttft_delta_ms": round(
            float(cache_recovery_metrics.get("bench.recovery.hot_followup_ttft_delta_ms", 0.0)),
            2,
        ),
        "cache_recovery.hot_prefix_affinity_hit_rate": round(
            float(cache_recovery_metrics.get("bench.recovery.hot_prefix_affinity_hit_rate", 0.0)),
            2,
        ),
        "cache_recovery.cold_l2_hit_rate": round(
            float(cache_recovery_metrics.get("bench.recovery.cold_l2_hit_rate", 0.0)),
            2,
        ),
        "cache_recovery.partial_restore_ratio_pct": round(
            float(cache_recovery_metrics.get("bench.recovery.partial_restore_ratio_pct", 0.0)),
            2,
        ),
    }

    return {
        "metrics": metrics,
        "cold_boot": {
            key: round(float(value), 2) if isinstance(value, (int, float)) else value
            for key, value in cold_boot_evidence.items()
        },
        "runtime_core": runtime_core_evidence,
        "operator": operator,
        "release_gate": release_gate_report,
    }


def compute_install_success_rate(install: dict[str, Any]) -> float:
    checks = install.get("checks", {})
    if not isinstance(checks, dict) or not checks:
        return 0.0
    success_count = sum(1 for value in checks.values() if value is True)
    return (success_count / len(checks)) * 100.0


def compute_benchmark_regression_pct(benchmarks: dict[str, Any], policy: dict[str, Any]) -> float:
    metrics = benchmarks.get("metrics", {})
    if not isinstance(metrics, dict):
        return 100.0

    worst_regression = 0.0
    for name, rule in policy.get("benchmarks", {}).items():
        value = metrics.get(name)
        if not isinstance(value, (int, float)):
            return 100.0
        if "max" in rule and float(value) > float(rule["max"]):
            regression = ((float(value) - float(rule["max"])) / float(rule["max"])) * 100.0
            worst_regression = max(worst_regression, regression)
        if "min" in rule and float(value) < float(rule["min"]):
            regression = ((float(rule["min"]) - float(value)) / float(rule["min"])) * 100.0
            worst_regression = max(worst_regression, regression)
    return worst_regression


def compute_release_smoke_pass_rate(report: dict[str, Any], policy: dict[str, Any]) -> float:
    sections = [
        all(report.get("install", {}).get("checks", {}).values()),
        report.get("benchmarks", {}).get("report_exists", False)
        and compute_benchmark_regression_pct(report.get("benchmarks", {}), policy) == 0.0,
        _training_sane(report.get("training", {}), policy),
        _recovery_sane(report.get("recovery", {}), policy),
        _runtime_core_sane(report.get("runtime_core", {}), policy),
    ]
    passed = sum(1 for section in sections if section)
    return (passed / len(sections)) * 100.0


def _metric_value(snapshot: dict[str, Any], key: str) -> float:
    values = snapshot.get("values", {})
    if not isinstance(values, dict):
        return 0.0
    return _rounded_float(values.get(key))


def _rounded_float(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return round(float(value), 2)


def _success_rate(successes: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((successes / total) * 100.0, 2)


def _build_maintenance_core(jobs_root: Path) -> MaintenanceCore:
    return _build_release_gate_maintenance_core(jobs_root)


def _seed_registry_state(core: MaintenanceCore, root: Path) -> None:
    dataset_root = _ensure_training_dataset(root)
    train_events = list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(root / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_root),
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            )
        )
    )
    artifact_path = train_events[-1].completed.output_path
    list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model=artifact_path,
                output_dir=str(root / "upload"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "adapter",
                    "artifact_path": artifact_path,
                    "adapter_name": "melix-dev-adapter",
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            )
        )
    )


def _training_sane(training: dict[str, Any], policy: dict[str, Any]) -> bool:
    rules = policy.get("training", {})
    duration = training.get("training_duration_ms")
    publish = training.get("adapter_publish_ms")
    return (
        isinstance(duration, (int, float))
        and isinstance(publish, (int, float))
        and float(duration) <= float(rules["training_duration_ms"]["max"])
        and float(publish) <= float(rules["adapter_publish_ms"]["max"])
    )


def _recovery_sane(recovery: dict[str, Any], policy: dict[str, Any]) -> bool:
    rules = policy.get("recovery", {})
    duration = recovery.get("restart_recovery_ms")
    success_rate = recovery.get("restart_recovery_success_rate")
    return (
        isinstance(duration, (int, float))
        and isinstance(success_rate, (int, float))
        and float(duration) <= float(rules["restart_recovery_ms"]["max"])
        and float(success_rate) >= float(rules["restart_recovery_success_rate"]["min"])
    )


def _runtime_core_sane(runtime_core: dict[str, Any], policy: dict[str, Any]) -> bool:
    if not isinstance(runtime_core, dict):
        return False
    return not _evaluate_section_metrics(runtime_core, policy.get("runtime_core", {}))
