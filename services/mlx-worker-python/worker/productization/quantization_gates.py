from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry

DEFAULT_QUANTIZATION_GATE_POLICY: dict[str, Any] = {
    "summary": {
        "profile_count": {"min": 7},
        "smoke_pass_rate": {"min": 100.0},
    },
    "profiles": {
        profile_id: {
            "job_ms": {"max": 50.0},
            "artifact_bytes": {"max": 4096.0},
            "manifest_bytes": {"max": 4096.0},
            "calibration_sample_count": {"min": 16.0},
            "smoke_test_passed": {"min": 1.0},
        }
        for profile_id in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
    },
}


def load_quantization_gate_policy(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_QUANTIZATION_GATE_POLICY)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_quantization_benchmark_evidence(
    jobs_root: str | Path,
    *,
    profiles: tuple[str, ...] = ("q2", "q3", "q4", "q5", "q6", "q7", "q8"),
) -> dict[str, Any]:
    core = _build_maintenance_core(jobs_root)
    profile_reports: dict[str, Any] = {}

    for profile_id in profiles:
        output_dir = Path(jobs_root) / profile_id
        request = maintenance_pb2.ConvertModelRequest(
            source_model="melix-dev-text",
            output_dir=str(output_dir),
            weight_quant=profile_id,
            kv_quant="q8",
            generate_manifest=True,
            run_smoke_test=True,
            ext={"operation": "quantize", "quant_profile_id": profile_id},
        )
        started_at = time.perf_counter()
        events = list(core.convert_model(request))
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        manifest = next(event.manifest for event in events if event.HasField("manifest"))
        payload = json.loads(manifest.manifest_json)
        profile_reports[profile_id] = {
            "quant_profile_id": profile_id,
            "job_ms": round(elapsed_ms, 3),
            "artifact_bytes": int(payload["artifact_bytes"]),
            "manifest_bytes": int(payload["manifest_bytes"]),
            "calibration_sample_count": int(payload["calibration"]["sample_count"]),
            "smoke_test_passed": bool(payload["compatibility"]["smoke_test_passed"]),
            "manifest_path": payload["manifest_path"],
            "artifact_path": payload["artifact_path"],
        }

    smoke_passes = sum(1 for report in profile_reports.values() if report["smoke_test_passed"])
    profile_count = len(profile_reports)
    return {
        "summary": {
            "profile_count": profile_count,
            "smoke_pass_rate": round((smoke_passes / max(profile_count, 1)) * 100.0, 2),
        },
        "profiles": profile_reports,
    }


def evaluate_quantization_gate(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    failures.extend(
        _evaluate_metrics(
            report.get("summary", {}),
            policy.get("summary", {}),
            prefix="summary",
        )
    )

    profile_rules = policy.get("profiles", {})
    reports = report.get("profiles", {})
    for profile_id, rules in profile_rules.items():
        profile_report = reports.get(profile_id)
        if not isinstance(profile_report, dict):
            failures.append(f"profiles.{profile_id} is missing")
            continue
        numeric_values = {
            **profile_report,
            "smoke_test_passed": 1.0 if profile_report.get("smoke_test_passed") else 0.0,
        }
        failures.extend(
            _evaluate_metrics(
                numeric_values,
                rules,
                prefix=f"profiles.{profile_id}",
            )
        )
    return failures


def _build_maintenance_core(jobs_root: str | Path) -> MaintenanceCore:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return MaintenanceCore(registry, Path(jobs_root))


def _evaluate_metrics(
    values: dict[str, Any],
    rules: dict[str, Any],
    *,
    prefix: str,
) -> list[str]:
    failures: list[str] = []
    for name, rule in rules.items():
        value = values.get(name)
        if not isinstance(value, (int, float)):
            failures.append(f"{prefix}.{name} is missing")
            continue
        numeric = float(value)
        minimum = rule.get("min")
        maximum = rule.get("max")
        if minimum is not None and numeric < float(minimum):
            failures.append(
                f"{prefix}.{name}={numeric:.2f} fell below minimum {float(minimum):.2f}"
            )
        if maximum is not None and numeric > float(maximum):
            failures.append(
                f"{prefix}.{name}={numeric:.2f} exceeded maximum {float(maximum):.2f}"
            )
    return failures
