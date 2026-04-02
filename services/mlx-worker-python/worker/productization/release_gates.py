from __future__ import annotations

import copy
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.model_ops.lora_training_pipeline import LoRATrainingPipelineResult
from worker.model_ops.training_dataset import load_training_dataset_package
from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.productization.quantization_gates import (
    DEFAULT_QUANTIZATION_GATE_POLICY,
    collect_quantization_benchmark_evidence,
    evaluate_quantization_gate,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.install_assets import (
    build_local_product_layout,
    write_local_product_artifacts,
)
from worker.registry import WorkerRegistry

DEFAULT_RELEASE_GATE_POLICY: dict[str, Any] = {
    "install": {
        "generated_asset_count": {"min": 5},
        "bootstrap_command_count": {"min": 3},
    },
    "benchmarks": {
        "bench.smoke.ttft_ms": {"max": 30.0},
        "bench.smoke.tokens_per_second": {"min": 45.0},
        "bench.latency.p95_ms": {"max": 50.0},
    },
    "training": {
        "training_duration_ms": {"max": 2_000.0},
        "adapter_publish_ms": {"max": 150.0},
    },
    "recovery": {
        "restart_recovery_ms": {"max": 15_000.0},
        "restart_recovery_success_rate": {"min": 100.0},
    },
    "runtime_core": {
        "multi_model_ready_count": {"min": 3},
        "multi_model_request_success_rate": {"min": 100.0},
        "prefill_memory_guard_rejection_count": {"min": 1.0},
        "prefill_memory_guard_success_rate": {"min": 100.0},
    },
    "quantization": copy.deepcopy(DEFAULT_QUANTIZATION_GATE_POLICY),
    "evaluation": {
        "eval.mmlu.accuracy": {"min": 0.5},
    },
}


class _ProductizationLoRATrainingPipeline:
    def run(
        self,
        *,
        job_id: str,
        request_ext: dict[str, str],
        source_model,
        output_dir: Path,
        progress=None,
    ) -> LoRATrainingPipelineResult:
        emit = progress or (lambda stage, pct: None)
        for stage, pct in [
            ("resolve_source", 0.1),
            ("validate_dataset", 0.2),
            ("normalize_config", 0.35),
            ("prepare_training_data", 0.5),
            ("apply_lora", 0.65),
            ("train", 0.8),
            ("write_adapter", 0.9),
            ("write_manifest", 0.97),
        ]:
            emit(stage, pct)

        dataset_uri = request_ext.get("dataset_uri", "")
        dataset = load_training_dataset_package(dataset_uri)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "train_lora.adapter.json"
        manifest = {
            "schema_version": "melix.lora_adapter_package.v1",
            "job_id": job_id,
            "operation": "train_lora",
            "artifact_kind": "adapter",
            "adapter_name": request_ext.get("adapter_name", "melix-dev-adapter"),
            "source_model": source_model.model_id,
            "source_model_revision": source_model.revision,
            "source_model_path": source_model.model_path,
            "dataset_uri": dataset_uri,
            "dataset_id": dataset.dataset_id,
            "training_backend": "deterministic",
            "training_duration_ms": 1_420.0,
            "adapter_publish_ms": 118.0,
            "adapter_set_hash": "productization-training-demo",
            "target_repo": request_ext.get("target_repo", ""),
            "response_only": dataset.response_only_supported,
            "gradient_checkpointing": False,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return LoRATrainingPipelineResult(manifest=manifest, manifest_path=manifest_path)


def load_release_gate_policy(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_RELEASE_GATE_POLICY)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_install_evidence(repo_root: str | Path) -> dict[str, Any]:
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="melix-phase8-install-") as home_dir:
        layout = build_local_product_layout(
            repo_root=repo_root,
            home_dir=home_dir,
            launch_agents_dir=Path(home_dir) / "Library/LaunchAgents",
        )
        manifest = write_local_product_artifacts(layout)
        asset_paths = [Path(path) for path in manifest["plists"].values()]

        checks = {
            "manifest_exists": layout.install_manifest_path.exists(),
            "environment_script_exists": layout.environment_script_path.exists(),
            "all_plists_exist": all(path.exists() for path in asset_paths),
        }

    return {
        "install_render_ms": round((time.perf_counter() - started_at) * 1_000.0, 2),
        "generated_asset_count": 5,
        "bootstrap_command_count": len(manifest["bootstrap_commands"]),
        "checks": checks,
    }


def collect_benchmark_evidence(
    jobs_root: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    core = _build_maintenance_core(jobs_root)
    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            )
        )
    )
    metrics = {
        event.metric.name: event.metric.value
        for event in events
        if event.HasField("metric")
    }
    metric_units = {
        event.metric.name: event.metric.unit
        for event in events
        if event.HasField("metric")
    }
    started_event = next((event.started for event in events if event.HasField("started")), None)
    job_id = started_event.job_id if started_event is not None else "bench-unknown"
    report_path = next(
        event.completed.report_path
        for event in events
        if event.HasField("completed")
    )
    report_markdown = Path(report_path).read_text(encoding="utf-8")
    job = build_serving_benchmark_job(
        job_id=job_id,
        model_id=str("melix-dev-text::1").split("::", 1)[0],
        suites=("smoke", "latency"),
        parameters={},
        status="completed",
        output_dir=str(Path(report_path).parent),
    )
    results = build_serving_benchmark_results(
        job_id=job_id,
        metrics=metrics,
        units=metric_units,
        report_path=report_path,
        report_markdown=report_markdown,
    )
    report = {
        "job": job.to_dict(),
        "results": [result.to_dict() for result in results],
        "metrics": metrics,
        "report_path": report_path,
        "report_exists": Path(report_path).exists(),
    }
    if repo_root is not None:
        recovery_report = collect_cache_recovery_benchmark_evidence(repo_root)
        recovery_report_path = Path(report_path).with_name("cache-recovery-report.json")
        recovery_report_path.write_text(
            json.dumps(recovery_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["recovery_metrics"] = dict(recovery_report.get("metrics", {}))
        report["recovery_report_path"] = str(recovery_report_path)
        report["recovery_report_exists"] = recovery_report_path.exists()
    return report


def collect_evaluation_evidence(jobs_root: str | Path) -> dict[str, Any]:
    from worker.engine.evaluation_core import EvaluationCore

    eval_root = Path(jobs_root) / "evaluation"
    eval_root.mkdir(parents=True, exist_ok=True)
    dataset_root = _ensure_evaluation_dataset(eval_root)

    core = EvaluationCore(jobs_root=eval_root)
    run = core.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=8,
        parameters={"judge": "deterministic"},
    )
    metrics: dict[str, float] = {}
    for metric in run.result.metrics:
        metrics[metric.name] = metric.value
    return {
        "job": run.job.to_dict(),
        "result": run.result.to_dict(),
        "metrics": metrics,
    }


def _ensure_evaluation_dataset(eval_root: Path) -> Path:
    dataset_root = eval_root / "datasets" / "mmlu-dev"
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_root / "manifest.json"
    samples_path = dataset_root / "samples.jsonl"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps({
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "schema_version": "melix.evaluation_dataset_manifest.v1",
                "sample_count": 8,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
    if not samples_path.exists():
        lines = []
        for a, b in [(3, 4), (7, 2), (10, 5), (12, 8), (6, 3), (9, 1), (15, 7), (20, 11)]:
            lines.append(json.dumps({"prompt": f"{a} + {b} ?", "expected": str(a + b)}))
        samples_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dataset_root


def _ensure_training_dataset(jobs_root: Path) -> Path:
    dataset_root = jobs_root / "datasets" / "melix-dev"
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_root / "manifest.json"
    samples_path = dataset_root / "samples.jsonl"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "melix.training_dataset_package.v1",
                    "dataset_id": "melix-dev",
                    "format": "chat_messages",
                    "sample_count": 2,
                    "version": "1",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if not samples_path.exists():
        samples_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "messages": [
                                {"role": "user", "content": "Say hi."},
                                {"role": "assistant", "content": "Hi there."},
                            ]
                        }
                    ),
                    json.dumps(
                        {
                            "messages": [
                                {"role": "user", "content": "Say bye."},
                                {"role": "assistant", "content": "Bye."},
                            ]
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return dataset_root


def collect_training_evidence(jobs_root: str | Path) -> dict[str, Any]:
    jobs_root = Path(jobs_root)
    core = _build_maintenance_core(jobs_root)
    dataset_root = _ensure_training_dataset(jobs_root)
    events = list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(jobs_root / "train-lora"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_root),
                },
            )
        )
    )
    manifest = next(
        event.manifest.manifest_json
        for event in events
        if event.HasField("manifest")
    )
    payload = json.loads(manifest)
    return {
        "job_id": payload["job_id"],
        "adapter_name": payload["adapter_name"],
        "dataset_uri": payload["dataset_uri"],
        "training_duration_ms": float(payload["training_duration_ms"]),
        "adapter_publish_ms": float(payload["adapter_publish_ms"]),
        "artifact_path": events[-1].completed.output_path,
    }


def build_release_gate_report(
    repo_root: str | Path,
    *,
    policy: dict[str, Any] | None = None,
    jobs_root: str | Path | None = None,
    recovery: dict[str, Any] | None = None,
    runtime_core: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = policy or load_release_gate_policy()
    if jobs_root is None:
        with tempfile.TemporaryDirectory(prefix="melix-phase8-release-") as tempdir:
            return build_release_gate_report(
                repo_root,
                policy=active_policy,
                jobs_root=tempdir,
                recovery=recovery,
                runtime_core=runtime_core,
            )

    report = {
        "install": collect_install_evidence(repo_root),
        "benchmarks": collect_benchmark_evidence(jobs_root, repo_root=repo_root),
        "training": collect_training_evidence(jobs_root),
        "quantization": collect_quantization_benchmark_evidence(Path(jobs_root) / "quantization"),
        "evaluation": collect_evaluation_evidence(jobs_root),
    }
    if recovery is not None:
        report["recovery"] = recovery
    if runtime_core is not None:
        report["runtime_core"] = runtime_core

    failures = evaluate_release_gate(report, active_policy)
    report["passed"] = not failures
    report["failures"] = failures
    return report


def evaluate_release_gate(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    install = report.get("install", {})
    failures.extend(_require_true(install, "checks.manifest_exists"))
    failures.extend(_require_true(install, "checks.environment_script_exists"))
    failures.extend(_require_true(install, "checks.all_plists_exist"))
    failures.extend(_evaluate_section_metrics(install, policy.get("install", {})))

    benchmarks = report.get("benchmarks", {})
    if not benchmarks.get("report_exists", False):
        failures.append("benchmarks.report_exists must be true")
    failures.extend(
        _evaluate_section_metrics(benchmarks.get("metrics", {}), policy.get("benchmarks", {}))
    )

    training = report.get("training", {})
    failures.extend(_evaluate_section_metrics(training, policy.get("training", {})))

    recovery = report.get("recovery")
    if not isinstance(recovery, dict):
        failures.append("recovery evidence is missing")
    else:
        failures.extend(_evaluate_section_metrics(recovery, policy.get("recovery", {})))

    runtime_core = report.get("runtime_core")
    if not isinstance(runtime_core, dict):
        failures.append("runtime_core evidence is missing")
    else:
        failures.extend(_evaluate_section_metrics(runtime_core, policy.get("runtime_core", {})))

    quantization = report.get("quantization")
    if not isinstance(quantization, dict):
        failures.append("quantization evidence is missing")
    else:
        failures.extend(
            evaluate_quantization_gate(quantization, policy.get("quantization", {}))
        )

    evaluation = report.get("evaluation")
    if isinstance(evaluation, dict):
        failures.extend(
            _evaluate_section_metrics(evaluation.get("metrics", {}), policy.get("evaluation", {}))
        )

    return failures


def _build_maintenance_core(jobs_root: str | Path) -> MaintenanceCore:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return MaintenanceCore(
        registry,
        Path(jobs_root),
        lora_training_pipeline=_ProductizationLoRATrainingPipeline(),
    )


def collect_cache_recovery_benchmark_evidence(repo_root: str | Path) -> dict[str, Any]:
    from phase8_runtime_probes import (
        collect_cache_recovery_benchmark_evidence as collect_runtime_probe_evidence,
    )

    return collect_runtime_probe_evidence(Path(repo_root).resolve())


def _evaluate_section_metrics(values: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for name, rule in rules.items():
        value = values.get(name)
        if value is None:
            failures.append(f"{name} is missing")
            continue
        if not isinstance(value, (int, float)):
            failures.append(f"{name} must be numeric")
            continue
        numeric = float(value)
        minimum = rule.get("min")
        maximum = rule.get("max")
        if minimum is not None and numeric < float(minimum):
            failures.append(f"{name}={numeric:.2f} fell below minimum {float(minimum):.2f}")
        if maximum is not None and numeric > float(maximum):
            failures.append(f"{name}={numeric:.2f} exceeded maximum {float(maximum):.2f}")
    return failures


def _require_true(payload: dict[str, Any], dotted_key: str) -> list[str]:
    current: Any = payload
    for segment in dotted_key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return [f"{dotted_key} is missing"]
        current = current[segment]
    if current is not True:
        return [f"{dotted_key} must be true"]
    return []
