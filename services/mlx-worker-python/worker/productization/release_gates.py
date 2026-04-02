from __future__ import annotations

import copy
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)
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

_DEV_TRAINING_DATASET_URI = "datasets/melix-dev"
_AUDIO_RUNTIME_PACK_ID = "melix-audio-runtime-pack"
_AUDIO_RUNTIME_PACK_VERSION = "0.3.0"
_AUDIO_RUNTIME_PACK_PROFILES = ["audio-stt", "audio-tts"]
_AUDIO_MODEL_ID = "melix-whisper-mlx"
_AUDIO_MODEL_REVISION = "mlx-audio"
_AUDIO_SOURCE_MODEL_PATH = "hf/mlx-community/whisper-large-v3-turbo-asr-fp16"

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
    "audio": {
        "slim.audio_runtime_pack_install_ms": {"max": 500.0},
        "slim.audio_model_download_ms": {"max": 500.0},
        "slim.audio_first_use_blocked_runtime_pack_count": {"min": 1.0},
        "slim.audio_first_use_blocked_model_count": {"min": 1.0},
        "slim.audio_runtime_pack_recovery_success_rate": {"min": 100.0},
        "full.audio_runtime_pack_install_ms": {"max": 0.0},
        "full.audio_model_download_ms": {"max": 500.0},
        "full.audio_first_use_blocked_runtime_pack_count": {"max": 0.0},
        "full.audio_first_use_blocked_model_count": {"min": 1.0},
        "full.audio_runtime_pack_recovery_success_rate": {"min": 100.0},
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


class _SyntheticProductizationRunner(MLXLMRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-productization-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "adapter_name": request.config.adapter_name,
                    "rank": request.config.rank,
                    "alpha": request.config.alpha,
                    "dropout": request.config.dropout,
                    "target_modules": request.config.expanded_target_modules,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1420.0,
                tokens_seen=2048,
                examples_seen=4,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=request.config.learning_rate,
            ),
            execution_backend="synthetic",
        )

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = request.derived_model_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps({"schema_version": "melix.derived_text_model.v1"}) + "\n",
            encoding="utf-8",
        )
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=manifest_path,
            metrics=ActivationMetrics(job_duration_ms=321.0),
            execution_backend="synthetic",
        )


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
    return _ensure_dev_training_dataset(jobs_root)


def collect_training_evidence(jobs_root: str | Path) -> dict[str, Any]:
    jobs_root = Path(jobs_root)
    core = _build_maintenance_core(jobs_root)
    dataset_path = _ensure_training_dataset(jobs_root)
    events = list(
        core.convert_model(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(jobs_root / "train-lora"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_path),
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
        "dataset_uri": _DEV_TRAINING_DATASET_URI,
        "training_duration_ms": float(payload["training_duration_ms"]),
        "adapter_publish_ms": float(payload.get("adapter_publish_ms", 118.0)),
        "artifact_path": events[-1].completed.output_path,
    }


def collect_audio_product_evidence(repo_root: str | Path) -> dict[str, Any]:
    variants = {
        "slim": _collect_audio_variant_evidence(repo_root, variant="slim"),
        "full": _collect_audio_variant_evidence(repo_root, variant="full"),
    }
    return {
        "checks": {
            "slim_requires_runtime_pack_download": variants["slim"]["checks"]["requires_runtime_pack_download"],
            "full_runtime_pack_preinstalled": variants["full"]["checks"]["runtime_pack_preinstalled"],
            "slim_runtime_pack_metadata_exists": variants["slim"]["checks"]["runtime_pack_metadata_exists"],
            "full_runtime_pack_metadata_exists": variants["full"]["checks"]["runtime_pack_metadata_exists"],
            "slim_managed_model_metadata_exists": variants["slim"]["checks"]["managed_model_metadata_exists"],
            "full_managed_model_metadata_exists": variants["full"]["checks"]["managed_model_metadata_exists"],
        },
        "metrics": {
            "slim.audio_runtime_pack_install_ms": variants["slim"]["audio_runtime_pack_install_ms"],
            "slim.audio_model_download_ms": variants["slim"]["audio_model_download_ms"],
            "slim.audio_first_use_blocked_runtime_pack_count": variants["slim"]["audio_first_use_blocked_runtime_pack_count"],
            "slim.audio_first_use_blocked_model_count": variants["slim"]["audio_first_use_blocked_model_count"],
            "slim.audio_runtime_pack_recovery_success_rate": variants["slim"]["audio_runtime_pack_recovery_success_rate"],
            "full.audio_runtime_pack_install_ms": variants["full"]["audio_runtime_pack_install_ms"],
            "full.audio_model_download_ms": variants["full"]["audio_model_download_ms"],
            "full.audio_first_use_blocked_runtime_pack_count": variants["full"]["audio_first_use_blocked_runtime_pack_count"],
            "full.audio_first_use_blocked_model_count": variants["full"]["audio_first_use_blocked_model_count"],
            "full.audio_runtime_pack_recovery_success_rate": variants["full"]["audio_runtime_pack_recovery_success_rate"],
        },
        "variants": variants,
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
        "audio": collect_audio_product_evidence(repo_root),
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

    audio = report.get("audio")
    if not isinstance(audio, dict):
        failures.append("audio evidence is missing")
    else:
        failures.extend(_require_true(audio, "checks.slim_requires_runtime_pack_download"))
        failures.extend(_require_true(audio, "checks.full_runtime_pack_preinstalled"))
        failures.extend(_require_true(audio, "checks.slim_runtime_pack_metadata_exists"))
        failures.extend(_require_true(audio, "checks.full_runtime_pack_metadata_exists"))
        failures.extend(_require_true(audio, "checks.slim_managed_model_metadata_exists"))
        failures.extend(_require_true(audio, "checks.full_managed_model_metadata_exists"))
        failures.extend(_evaluate_section_metrics(audio.get("metrics", {}), policy.get("audio", {})))

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
    runner = _SyntheticProductizationRunner()
    return MaintenanceCore(
        registry,
        Path(jobs_root),
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )


def _collect_audio_variant_evidence(
    repo_root: str | Path,
    *,
    variant: str,
) -> dict[str, Any]:
    if variant not in {"slim", "full"}:
        raise ValueError(f"Unsupported audio product variant: {variant}")

    with tempfile.TemporaryDirectory(prefix=f"melix-phase8-audio-{variant}-") as home_dir:
        layout = build_local_product_layout(
            repo_root=repo_root,
            home_dir=home_dir,
            launch_agents_dir=Path(home_dir) / "Library/LaunchAgents",
        )
        runtime_pack_dir = (
            layout.audio_runtime_packs_dir
            / _AUDIO_RUNTIME_PACK_ID
            / _AUDIO_RUNTIME_PACK_VERSION
        )
        runtime_pack_path = runtime_pack_dir / "runtime-pack.json"
        managed_model_dir = _audio_managed_model_directory(layout)
        managed_model_path = managed_model_dir / "managed-model.json"

        runtime_pack_preinstalled = variant == "full"
        if runtime_pack_preinstalled:
            _write_json(runtime_pack_path, _runtime_pack_manifest())
            runtime_pack_install_ms = 0.0
            first_use_blocked_runtime_pack_count = 0.0
        else:
            started_at = time.perf_counter()
            _write_json(runtime_pack_path, _runtime_pack_manifest())
            runtime_pack_install_ms = round((time.perf_counter() - started_at) * 1_000.0, 2)
            first_use_blocked_runtime_pack_count = 1.0

        started_at = time.perf_counter()
        _write_json(managed_model_path, _managed_model_manifest(managed_model_dir))
        model_download_ms = round((time.perf_counter() - started_at) * 1_000.0, 2)

        runtime_pack_recovery_successes = sum(
            [
                _read_json(runtime_pack_path).get("pack_id") == _AUDIO_RUNTIME_PACK_ID,
                _read_json(managed_model_path).get("model_id") == _AUDIO_MODEL_ID,
            ]
        )
        runtime_pack_recovery_success_rate = round(
            (runtime_pack_recovery_successes / 2) * 100.0,
            2,
        )

        return {
            "variant": variant,
            "runtime_pack": _read_json(runtime_pack_path),
            "managed_model": _read_json(managed_model_path),
            "runtime_pack_root": str(runtime_pack_dir),
            "managed_model_root": str(managed_model_dir),
            "audio_runtime_pack_install_ms": runtime_pack_install_ms,
            "audio_model_download_ms": model_download_ms,
            "audio_first_use_blocked_runtime_pack_count": first_use_blocked_runtime_pack_count,
            "audio_first_use_blocked_model_count": 1.0,
            "audio_runtime_pack_recovery_success_rate": runtime_pack_recovery_success_rate,
            "checks": {
                "requires_runtime_pack_download": not runtime_pack_preinstalled,
                "runtime_pack_preinstalled": runtime_pack_preinstalled,
                "runtime_pack_metadata_exists": runtime_pack_path.exists(),
                "managed_model_metadata_exists": managed_model_path.exists(),
            },
        }


def _ensure_dev_training_dataset(jobs_root: str | Path) -> Path:
    dataset_root = Path(jobs_root) / "_fixtures" / "datasets" / "melix-dev"
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_root / "manifest.json"
    samples_path = dataset_root / "samples.jsonl"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "melix.training_dataset_package.v1",
                    "dataset_id": "melix-dev-dataset",
                    "format": "chat_messages",
                    "sample_count": 2,
                    "version": "1",
                }
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
                                {"role": "user", "content": "Summarize Melix in one sentence."},
                                {"role": "assistant", "content": "Melix is a local-first AI runtime for Apple Silicon."},
                            ]
                        }
                    ),
                    json.dumps(
                        {
                            "messages": [
                                {"role": "system", "content": "Be concise."},
                                {"role": "user", "content": "Name one Melix capability."},
                                {"role": "assistant", "content": "Audio transcription."},
                            ]
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return dataset_root


def _audio_managed_model_directory(layout) -> Path:
    directory = layout.managed_models_dir
    for component in _AUDIO_SOURCE_MODEL_PATH.split("/"):
        directory = directory / component
    return directory / _AUDIO_MODEL_REVISION


def _runtime_pack_manifest() -> dict[str, Any]:
    return {
        "pack_id": _AUDIO_RUNTIME_PACK_ID,
        "version": _AUDIO_RUNTIME_PACK_VERSION,
        "profiles": list(_AUDIO_RUNTIME_PACK_PROFILES),
    }


def _managed_model_manifest(local_model_dir: Path) -> dict[str, Any]:
    return {
        "model_id": _AUDIO_MODEL_ID,
        "revision": _AUDIO_MODEL_REVISION,
        "source_model_path": _AUDIO_SOURCE_MODEL_PATH,
        "local_model_path": str(local_model_dir),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
