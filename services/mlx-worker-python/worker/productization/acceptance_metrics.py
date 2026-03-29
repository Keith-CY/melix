from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.release_gates import load_release_gate_policy
from worker.registry import WorkerRegistry


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


def build_phase8_metrics_report(
    *,
    cold_boot_to_ready_ms: float | None = None,
    cold_boot: dict[str, Any] | None = None,
    operator: dict[str, Any],
    release_gate_report: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = policy or load_release_gate_policy()
    cold_boot_evidence = dict(cold_boot or {})
    if cold_boot_to_ready_ms is not None:
        cold_boot_evidence.setdefault("cold_boot_to_ready_ms", cold_boot_to_ready_ms)
    recovery = release_gate_report["recovery"]

    metrics = {
        "desktop.cold_boot_to_ready_ms": round(
            float(cold_boot_evidence["cold_boot_to_ready_ms"]), 2
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
        "desktop.snapshot_restore_ms": round(
            float(recovery.get("snapshot_restore_ms", 0.0)), 2
        ),
        "desktop.restart_recovery_ms": round(
            float(recovery["restart_recovery_ms"]), 2
        ),
        "desktop.crash_recovery_success_rate": float(
            recovery["restart_recovery_success_rate"]
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
    }

    return {
        "metrics": metrics,
        "cold_boot": {
            key: round(float(value), 2) if isinstance(value, (int, float)) else value
            for key, value in cold_boot_evidence.items()
        },
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
    ]
    passed = sum(1 for section in sections if section)
    return (passed / len(sections)) * 100.0


def _build_maintenance_core(jobs_root: Path) -> MaintenanceCore:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return MaintenanceCore(registry, jobs_root)


def _seed_registry_state(core: MaintenanceCore, root: Path) -> None:
    train_events = list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(root / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": "datasets/melix-dev",
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
