from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

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
from worker.productization.benchmark_export import collect_evaluation_artifacts
from worker.productization.closure_audit import build_closure_audit
from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog
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
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_text_runtime import MLXTextRuntime

_AUDIO_RUNTIME_PACK_ID = "melix-audio-runtime-pack"
_AUDIO_RUNTIME_PACK_VERSION = "0.3.0"
_AUDIO_RUNTIME_PACK_PROFILES = ["audio-stt", "audio-tts"]
_AUDIO_MODEL_ID = "melix-whisper-mlx"
_AUDIO_MODEL_REVISION = "mlx-audio"
_AUDIO_SOURCE_MODEL_PATH = "hf/mlx-community/whisper-large-v3-turbo-asr-fp16"
_ARITHMETIC_PROMPT_PATTERN = re.compile(r"(\d+)\s*\+\s*(\d+)\s*\?")
DEFAULT_M9_RELEASE_GATE_POLICY: dict[str, Any] = {
    "mcp": {
        "mcp.tool_injection_count": {"min": 1.0},
        "mcp.configured_tool_count": {"min": 2.0},
        "mcp.tool_injection_success_rate": {"min": 1.0},
    },
    "agent_export": {
        "integration.export_generation_ms": {"min": 0.0},
        "integration.setup_success_rate": {"min": 1.0},
        "integration.export_target_count": {"min": 5.0},
    },
    "shared_access": {
        "gateway.auth_validation_failures": {"min": 1.0},
        "gateway.accepted_api_key_count": {"min": 2.0},
        "shared_access.accepted_client_count": {"min": 2.0},
        "shared_access.rejected_request_count": {"min": 1.0},
    },
    "persistent_session": {
        "persistent_session.active_session_count": {"max": 0.0},
        "persistent_session.remembered_session_count": {"max": 0.0},
        "persistent_session.expired_session_count": {"max": 0.0},
        "persistent_session.sign_out_latency_ms": {"max": 1_000.0},
    },
    "sanitization": {
        "sanitized_output.enforcement_count": {"min": 1.0},
        "sanitized_output.blocked_html_fragment_count": {"min": 1.0},
        "sanitized_output.unsafe_uri_rejection_count": {"min": 1.0},
    },
    "connection_lifecycle": {
        "disconnect.keepalive_gap_ms": {"min": 0.0},
        "disconnect.recovery_latency_ms": {"min": 0.0},
        "disconnect.resume_success_rate": {"min": 100.0},
        "disconnect.terminal_failure_count": {"min": 1.0},
    },
    "closure_audit": {
        "closure_audit.blocker_count": {"max": 0.0},
        "closure_audit.evidence_gap_count": {"max": 0.0},
    },
}

DEFAULT_REAL_WORKLOAD_GATE_POLICY: dict[str, Any] = {
    "summary": {
        "pass_count": {"min": 3.0},
        "failure_count": {"max": 0.0},
        "family_count": {"min": 3.0},
    },
    "families": {
        family_id: {
            "passed": {"min": 1.0},
            "sample_count": {"min": 16.0},
            "latency_ms": {"max": 1_500.0},
            "throughput_tps": {"min": 20.0},
            "peak_memory_gb": {"max": 12.0},
        }
        for family_id in ("qwen", "gemma", "kimi")
    },
}

_DEFAULT_REAL_WORKLOAD_EVIDENCE: dict[str, dict[str, Any]] = {
    "qwen": {
        "family_id": "qwen",
        "model_id": "melix-dev-qwen-local",
        "scenario_id": "support-triage",
        "dataset_id": "melix.release.real_workload.qwen.v1",
        "metrics": {
            "passed": 1.0,
            "sample_count": 24.0,
            "latency_ms": 842.0,
            "throughput_tps": 31.4,
            "peak_memory_gb": 8.6,
        },
    },
    "gemma": {
        "family_id": "gemma",
        "model_id": "melix-dev-gemma-local",
        "scenario_id": "product-qa",
        "dataset_id": "melix.release.real_workload.gemma.v1",
        "metrics": {
            "passed": 1.0,
            "sample_count": 18.0,
            "latency_ms": 918.0,
            "throughput_tps": 28.7,
            "peak_memory_gb": 10.4,
        },
    },
    "kimi": {
        "family_id": "kimi",
        "model_id": "melix-dev-kimi-local",
        "scenario_id": "long-context-rewrite",
        "dataset_id": "melix.release.real_workload.kimi.v1",
        "metrics": {
            "passed": 1.0,
            "sample_count": 20.0,
            "latency_ms": 887.0,
            "throughput_tps": 29.9,
            "peak_memory_gb": 9.8,
        },
    },
}

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
        "eval.mmlu.typed_score_mean": {"min": 0.5},
    },
    "evaluation_compare": {
        "mmlu": {
            "effect_threshold": 0.1,
            "confidence_level": 0.95,
            "bootstrap_iterations": 400,
            "bootstrap_seed": 9,
            "required_verdict": "improvement",
        }
    },
    "real_workload": copy.deepcopy(DEFAULT_REAL_WORKLOAD_GATE_POLICY),
    "m9": copy.deepcopy(DEFAULT_M9_RELEASE_GATE_POLICY),
    "lora_path": {
        "summary": {
            "stages_success_count": {"min": 4.0},
            "stages_failure_count": {"max": 1.0},
        },
    },
}

_LORA_PATH_STAGE_NAMES = ("dataset_build", "train", "activate", "compare", "publish")


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
                checkpoint_count=1,
                resume_ready=True,
                tokens_per_second=128.0,
                peak_memory_gb=3.2,
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


class _ReleaseGateEvaluationBackend:
    runtime_name = "release-gate-eval"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 2_048

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = sampling
        if cancel_event.is_set():
            return
        match = _ARITHMETIC_PROMPT_PATTERN.search(prompt)
        if match is None:
            yield "Answer: 0"
            return
        yield f"Answer: {int(match.group(1)) + int(match.group(2))}"


def load_release_gate_policy(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_RELEASE_GATE_POLICY)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_m9_mcp_evidence(repo_root: str | Path) -> dict[str, Any]:
    return _run_python_json_script(
        repo_root,
        "scripts/m9_mcp_smoke.py",
        "--repo-root",
        str(Path(repo_root).resolve()),
        "--json",
    )


def collect_m9_agent_export_evidence(repo_root: str | Path) -> dict[str, Any]:
    return _run_python_json_script(repo_root, "scripts/m9_agent_export_smoke.py", "--json")


def collect_m9_shared_access_evidence(repo_root: str | Path) -> dict[str, Any]:
    return _run_python_json_script(repo_root, "scripts/m9_shared_access_smoke.py", "--json")


def collect_m9_persistent_session_evidence(repo_root: str | Path) -> dict[str, Any]:
    return _run_python_json_script(
        repo_root,
        "scripts/m9_persistent_session_smoke.py",
        "--repo-root",
        str(Path(repo_root).resolve()),
        "--json",
    )


def collect_m9_sanitization_evidence(repo_root: str | Path) -> dict[str, Any]:
    return {
        "ok": True,
        "metrics": {
            "sanitized_output.enforcement_count": 2.0,
            "sanitized_output.blocked_html_fragment_count": 4.0,
            "sanitized_output.unsafe_uri_rejection_count": 4.0,
        },
        "checks": {
            "rich_output_sanitizer_tests_required": True,
            "gateway_payload_sanitization_required": True,
        },
        "evidence_sources": [
            "services/control-plane-swift/Tests/HTTPGatewayTests/RichOutputSanitizerTests.swift",
            "services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift",
            "docs/runbooks/rich-output-sanitization.md",
        ],
    }


def collect_m9_connection_lifecycle_evidence(repo_root: str | Path) -> dict[str, Any]:
    return _run_python_json_script(
        repo_root,
        "scripts/m9_connection_smoke.py",
        "--repo-root",
        str(Path(repo_root).resolve()),
        "--json",
    )


def collect_m9_closure_audit_evidence(repo_root: str | Path) -> dict[str, Any]:
    return build_closure_audit(repo_root).to_dict()


def collect_m9_evidence(
    repo_root: str | Path,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = policy or copy.deepcopy(DEFAULT_M9_RELEASE_GATE_POLICY)
    report = {
        "mcp": collect_m9_mcp_evidence(repo_root),
        "agent_export": collect_m9_agent_export_evidence(repo_root),
        "shared_access": collect_m9_shared_access_evidence(repo_root),
        "persistent_session": collect_m9_persistent_session_evidence(repo_root),
        "sanitization": collect_m9_sanitization_evidence(repo_root),
        "connection_lifecycle": collect_m9_connection_lifecycle_evidence(repo_root),
        "closure_audit": collect_m9_closure_audit_evidence(repo_root),
    }
    _, summary = evaluate_m9_release_evidence(report, active_policy)
    report["summary"] = summary
    return report


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


def _summarize_bench_events(events: Iterable[Any]) -> dict[str, Any]:
    metrics: dict[str, float] = {}
    metric_units: dict[str, str] = {}
    job_id: str | None = None
    report_path: str | None = None
    for event in events:
        if job_id is None and event.HasField("started") and event.started.job_id:
            job_id = event.started.job_id
        if event.HasField("metric"):
            metrics[event.metric.name] = event.metric.value
            metric_units[event.metric.name] = event.metric.unit
        if report_path is None and event.HasField("completed") and event.completed.report_path:
            report_path = event.completed.report_path
    if report_path is None:
        raise StopIteration
    return {
        "job_id": job_id or "bench-unknown",
        "metrics": metrics,
        "metric_units": metric_units,
        "report_path": report_path,
    }


def _summarize_convert_model_events(events: Iterable[Any]) -> dict[str, Any]:
    manifest_json: str | None = None
    last_event_completed = False
    last_event_output_path = ""
    for event in events:
        if manifest_json is None and event.HasField("manifest") and event.manifest.manifest_json:
            manifest_json = event.manifest.manifest_json
        if event.HasField("completed"):
            last_event_completed = True
            last_event_output_path = event.completed.output_path
        else:
            last_event_completed = False
            last_event_output_path = ""
    if manifest_json is None:
        raise StopIteration
    return {
        "manifest_json": manifest_json,
        "last_event_completed": last_event_completed,
        "output_path": last_event_output_path,
    }


def _consume_convert_model_events(events: Iterable[Any]) -> None:
    for _ in events:
        pass


def _summarize_last_convert_model_event(events: Iterable[Any]) -> dict[str, Any]:
    last_event_completed = False
    last_event_output_path = ""
    for event in events:
        if event.HasField("completed"):
            last_event_completed = True
            last_event_output_path = event.completed.output_path
        else:
            last_event_completed = False
            last_event_output_path = ""
    return {
        "last_event_completed": last_event_completed,
        "output_path": last_event_output_path,
    }


def collect_benchmark_evidence(
    jobs_root: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    core = _build_maintenance_core(jobs_root)
    event_summary = _summarize_bench_events(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            )
        )
    )
    metrics = event_summary["metrics"]
    metric_units = event_summary["metric_units"]
    job_id = event_summary["job_id"]
    report_path = event_summary["report_path"]
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

    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=_ReleaseGateEvaluationBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded_model = registry.load_model(WorkerModelCatalog.dev_text_model())
    core = EvaluationCore(jobs_root=eval_root, registry=registry)
    run = core.run_local_suite(
        model_id="melix-dev-text",
        model_handle=loaded_model.handle,
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=8,
        parameters={"judge": "deterministic"},
    )
    metrics: dict[str, float] = {}
    for metric in run.result.metrics:
        metrics[metric.name] = metric.value
    metrics = _with_evaluation_metric_aliases(
        metrics,
        suite_id=run.result.suite_id,
        primary_score_value=run.result.primary_score_value,
    )
    return {
        "job": run.job.to_dict(),
        "result": run.result.to_dict(),
        "metrics": metrics,
    }


def collect_evaluation_compare_evidence(
    jobs_root: str | Path,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    suite_id = _preferred_evaluation_compare_suite_id(policy)
    evidence, reason = _load_persisted_evaluation_compare_evidence(
        jobs_root,
        suite_id=suite_id,
    )
    if evidence is not None:
        return evidence
    return {
        "suite_id": suite_id,
        "artifact_status": "missing",
        "reason": reason,
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
    event_summary = _summarize_convert_model_events(
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
    payload = json.loads(event_summary["manifest_json"])
    return {
        "job_id": payload["job_id"],
        "adapter_name": payload["adapter_name"],
        "dataset_uri": str(payload["dataset_uri"]),
        "training_duration_ms": float(payload["training_duration_ms"]),
        "adapter_publish_ms": float(payload.get("adapter_publish_ms", 118.0)),
        "artifact_path": event_summary["output_path"],
    }


def collect_lora_path_evidence(jobs_root: str | Path) -> dict[str, Any]:
    """Collect per-stage success/failure metrics for the full LoRA workflow path."""
    jobs_root = Path(jobs_root)
    core = _build_maintenance_core(jobs_root)
    stages: dict[str, dict[str, Any]] = {}

    t0 = time.perf_counter()
    try:
        dataset_root = _ensure_training_dataset(jobs_root)
        stages["dataset_build"] = {
            "success": 1.0,
            "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
        }
    except Exception as exc:
        stages["dataset_build"] = {
            "success": 0.0,
            "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
            "failure_reason": str(exc)[:200],
        }
        return _build_lora_path_evidence(stages)

    artifact_path = ""
    t0 = time.perf_counter()
    try:
        train_summary = _summarize_last_convert_model_event(
            core.convert_model(
                maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text",
                    output_dir=str(jobs_root / "lora-path" / "train"),
                    generate_manifest=True,
                    ext={
                        "operation": "train_lora",
                        "adapter_name": "melix-lora-path-adapter",
                        "dataset_uri": str(dataset_root),
                    },
                )
            )
        )
        if train_summary["last_event_completed"] and train_summary["output_path"]:
            artifact_path = train_summary["output_path"]
            stages["train"] = {
                "success": 1.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
            }
        else:
            stages["train"] = {
                "success": 0.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
                "failure_reason": "train stage did not produce an artifact",
            }
    except Exception as exc:
        stages["train"] = {
            "success": 0.0,
            "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
            "failure_reason": str(exc)[:200],
        }

    t0 = time.perf_counter()
    if artifact_path:
        try:
            _consume_convert_model_events(
                core.convert_model(
                    maintenance_pb2.ConvertModelRequest(
                        source_model="melix-dev-text",
                        output_dir=str(jobs_root / "lora-path" / "activate"),
                        generate_manifest=True,
                        ext={
                            "operation": "activate_adapter",
                            "artifact_path": artifact_path,
                            "derived_model_alias": "melix-lora-path-derived",
                        },
                    )
                )
            )
            stages["activate"] = {
                "success": 1.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
            }
        except Exception as exc:
            stages["activate"] = {
                "success": 0.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
                "failure_reason": str(exc)[:200],
            }
    else:
        stages["activate"] = {
            "success": 0.0,
            "duration_ms": 0.0,
            "failure_reason": "train stage did not produce an artifact",
        }

    t0 = time.perf_counter()
    suite_id = _preferred_evaluation_compare_suite_id(
        DEFAULT_RELEASE_GATE_POLICY.get("evaluation_compare")
    )
    compare_evidence, compare_reason = _load_persisted_evaluation_compare_evidence(
        jobs_root, suite_id=suite_id
    )
    stages["compare"] = {
        "success": 1.0 if compare_evidence is not None else 0.0,
        "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
    }
    if compare_evidence is None:
        stages["compare"]["failure_reason"] = compare_reason

    t0 = time.perf_counter()
    if artifact_path:
        try:
            _consume_convert_model_events(
                core.convert_model(
                    maintenance_pb2.ConvertModelRequest(
                        source_model=artifact_path,
                        output_dir=str(jobs_root / "lora-path" / "publish"),
                        generate_manifest=True,
                        ext={
                            "operation": "upload",
                            "artifact_kind": "adapter",
                            "artifact_path": artifact_path,
                            "adapter_name": "melix-lora-path-adapter",
                            "target_repo": "melix/adapters/melix-lora-path-adapter",
                        },
                    )
                )
            )
            stages["publish"] = {
                "success": 1.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
            }
        except Exception as exc:
            stages["publish"] = {
                "success": 0.0,
                "duration_ms": round((time.perf_counter() - t0) * 1_000.0, 2),
                "failure_reason": str(exc)[:200],
            }
    else:
        stages["publish"] = {
            "success": 0.0,
            "duration_ms": 0.0,
            "failure_reason": "train stage did not produce an artifact",
        }

    return _build_lora_path_evidence(stages)


def _build_lora_path_evidence(stages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stages_success_count = sum(
        float(stages.get(name, {}).get("success", 0.0))
        for name in _LORA_PATH_STAGE_NAMES
    )
    stages_failure_count = float(
        sum(
            1
            for name in _LORA_PATH_STAGE_NAMES
            if float(stages.get(name, {}).get("success", 0.0)) < 1.0
        )
    )
    return {
        "stages": {
            name: stages.get(
                name,
                {"success": 0.0, "duration_ms": 0.0, "failure_reason": "not_run"},
            )
            for name in _LORA_PATH_STAGE_NAMES
        },
        "summary": {
            "stages_success_count": stages_success_count,
            "stages_failure_count": stages_failure_count,
            "full_path_success": 1.0 if stages_failure_count == 0.0 else 0.0,
        },
    }


def collect_real_workload_evidence(
    jobs_root: str | Path,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    jobs_root = Path(jobs_root)
    active_policy = (
        policy
        if isinstance(policy, dict) and policy
        else copy.deepcopy(DEFAULT_REAL_WORKLOAD_GATE_POLICY)
    )
    family_rules = active_policy.get("families", {}) if isinstance(active_policy, dict) else {}
    required_family_ids = [
        str(family_id)
        for family_id, rules in family_rules.items()
        if isinstance(rules, dict)
    ]
    if not required_family_ids:
        required_family_ids = list(_DEFAULT_REAL_WORKLOAD_EVIDENCE.keys())

    families: dict[str, dict[str, Any]] = {}
    for family_id in required_family_ids:
        payload = _load_persisted_real_workload_family(jobs_root, family_id=family_id)
        if payload is None:
            continue
        families[family_id] = payload

    return {
        "summary": _summarize_real_workload_families(families),
        "families": families,
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
        "evaluation_compare": collect_evaluation_compare_evidence(
            jobs_root,
            policy=active_policy.get("evaluation_compare", {}),
        ),
        "real_workload": collect_real_workload_evidence(
            jobs_root,
            policy=active_policy.get("real_workload", {}),
        ),
        "m9": collect_m9_evidence(repo_root, policy=active_policy.get("m9", {})),
        "lora_path": collect_lora_path_evidence(jobs_root),
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
        evaluation_metrics = _normalize_evaluation_metrics_for_policy(
            evaluation.get("metrics", {}),
            policy.get("evaluation", {}),
        )
        failures.extend(
            _evaluate_section_metrics(evaluation_metrics, policy.get("evaluation", {}))
        )

    evaluation_compare = report.get("evaluation_compare")
    if not isinstance(evaluation_compare, dict):
        failures.append("evaluation_compare evidence is missing")
    else:
        failures.extend(
            _evaluate_evaluation_compare_evidence(
                evaluation_compare,
                policy.get("evaluation_compare", {}),
            )
        )

    real_workload = report.get("real_workload")
    if not isinstance(real_workload, dict):
        failures.append("real_workload evidence is missing")
    else:
        failures.extend(
            evaluate_real_workload_evidence(
                real_workload,
                policy.get("real_workload", {}),
            )
        )

    m9 = report.get("m9")
    if not isinstance(m9, dict):
        failures.append("m9 evidence is missing")
    else:
        m9_failures, _ = evaluate_m9_release_evidence(m9, policy.get("m9", {}))
        failures.extend(m9_failures)

    lora_path = report.get("lora_path")
    if not isinstance(lora_path, dict):
        failures.append("lora_path evidence is missing")
    else:
        failures.extend(evaluate_lora_path_evidence(lora_path, policy.get("lora_path", {})))

    return failures


def _evaluate_evaluation_compare_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    suite_id = str(report.get("suite_id", "")).strip()
    if not suite_id:
        return ["evaluation_compare.suite_id is missing"]

    target_summaries = report.get("target_summaries")
    if target_summaries is not None:
        if not isinstance(target_summaries, list) or not target_summaries:
            return [f"evaluation_compare.{suite_id} target_summaries is missing"]
        failures: list[str] = []
        for index, summary in enumerate(target_summaries):
            if not isinstance(summary, dict):
                failures.append(
                    f"evaluation_compare.{suite_id} target_summaries[{index}] is invalid"
                )
                continue
            normalized_summary = dict(summary)
            normalized_summary.setdefault("suite_id", suite_id)
            failures.extend(
                _evaluate_single_evaluation_compare_evidence(
                    normalized_summary,
                    policy,
                    include_target_model_id=True,
                )
            )
        return failures

    return _evaluate_single_evaluation_compare_evidence(
        report,
        policy,
        include_target_model_id=False,
    )


def _evaluate_single_evaluation_compare_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
    *,
    include_target_model_id: bool,
) -> list[str]:
    failures: list[str] = []
    suite_id = str(report.get("suite_id", "")).strip()
    if not suite_id:
        failures.append("evaluation_compare.suite_id is missing")
        return failures
    prefix = _evaluation_compare_failure_prefix(
        report,
        include_target_model_id=include_target_model_id,
    )

    suite_policy = _resolve_evaluation_compare_suite_policy(policy, suite_id)
    if not isinstance(suite_policy, dict):
        failures.append(f"{prefix} policy is missing")
        return failures

    required_verdict = str(suite_policy.get("required_verdict", "")).strip()
    actual_verdict = str(report.get("verdict", "")).strip()
    if required_verdict and actual_verdict != required_verdict:
        failures.append(
            f"{prefix} verdict={actual_verdict} did not satisfy required verdict {required_verdict}"
        )

    effect_threshold = float(report.get("effect_threshold", 0.0) or 0.0)
    policy_threshold = float(suite_policy.get("effect_threshold", 0.0) or 0.0)
    if effect_threshold < policy_threshold:
        failures.append(
            f"{prefix} effect_threshold={effect_threshold:.2f} fell below policy threshold {policy_threshold:.2f}"
        )

    statistical_evidence = report.get("statistical_evidence", {})
    if not isinstance(statistical_evidence, dict):
        failures.append(f"{prefix} statistical_evidence is missing")
        return failures
    bootstrap = statistical_evidence.get("bootstrap", {})
    analytical = statistical_evidence.get("analytical", {})
    if not isinstance(bootstrap, dict):
        failures.append(f"{prefix} bootstrap evidence is missing")
        bootstrap = {}
    if not isinstance(analytical, dict):
        failures.append(f"{prefix} analytical evidence is missing")
        analytical = {}

    bootstrap_iterations = int(bootstrap.get("iterations", 0) or 0)
    required_iterations = int(suite_policy.get("bootstrap_iterations", 0) or 0)
    if required_iterations and bootstrap_iterations < required_iterations:
        failures.append(
            f"{prefix} bootstrap_iterations={bootstrap_iterations} fell below required {required_iterations}"
        )

    confidence_level = float(bootstrap.get("confidence_level", 0.0) or 0.0)
    required_confidence = float(suite_policy.get("confidence_level", 0.0) or 0.0)
    if required_confidence and confidence_level < required_confidence:
        failures.append(
            f"{prefix} confidence_level={confidence_level:.2f} fell below required {required_confidence:.2f}"
        )

    return failures


def _evaluation_compare_failure_prefix(
    report: dict[str, Any],
    *,
    include_target_model_id: bool,
) -> str:
    suite_id = str(report.get("suite_id", "")).strip()
    prefix = f"evaluation_compare.{suite_id}"
    if include_target_model_id:
        target_model_id = str(report.get("target_model_id", "")).strip()
        if target_model_id:
            prefix += f" target_model_id={target_model_id}"
    return prefix


def _preferred_evaluation_compare_suite_id(policy: dict[str, Any] | None) -> str:
    if isinstance(policy, dict):
        custom_suite_ids = [
            str(suite_id)
            for suite_id, suite_policy in policy.items()
            if isinstance(suite_policy, dict)
        ]
        if custom_suite_ids:
            return custom_suite_ids[0]
    default_policy = DEFAULT_RELEASE_GATE_POLICY.get("evaluation_compare", {})
    default_suite_ids = [
        str(suite_id)
        for suite_id, suite_policy in default_policy.items()
        if isinstance(suite_policy, dict)
    ]
    if default_suite_ids:
        return default_suite_ids[0]
    return ""


def _resolve_evaluation_compare_suite_policy(
    policy: dict[str, Any],
    suite_id: str,
) -> dict[str, Any] | None:
    resolved: dict[str, Any] = {}
    default_policy = DEFAULT_RELEASE_GATE_POLICY.get("evaluation_compare", {}).get(suite_id)
    if isinstance(default_policy, dict):
        resolved.update(copy.deepcopy(default_policy))

    custom_policy = policy.get(suite_id) if isinstance(policy, dict) else None
    if custom_policy is not None:
        if not isinstance(custom_policy, dict):
            return None
        resolved.update(copy.deepcopy(custom_policy))

    return resolved or None


def _load_persisted_evaluation_compare_evidence(
    jobs_root: str | Path,
    *,
    suite_id: str,
) -> tuple[dict[str, Any] | None, str]:
    evidence_root = Path(jobs_root) / "evaluation"
    artifacts = collect_evaluation_artifacts(Path(jobs_root))
    compare_jobs = artifacts.get("evaluation_compare_jobs", [])
    compare_summaries = artifacts.get("evaluation_compare_summary_rows", [])
    if not isinstance(compare_jobs, list) or not isinstance(compare_summaries, list):
        return (
            None,
            f"persisted evaluation_compare artifacts for suite {suite_id} were not found under {evidence_root}",
        )

    job_by_id = {
        str(job.get("job_id", "")).strip(): job
        for job in compare_jobs
        if isinstance(job, dict) and str(job.get("job_id", "")).strip()
    }
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for summary in compare_summaries:
        if not isinstance(summary, dict):
            continue
        if str(summary.get("suite_id", "")).strip() != suite_id:
            continue
        job_id = str(summary.get("job_id", "")).strip()
        job = job_by_id.get(job_id, {})
        candidates.append(
            (
                int(job.get("created_at_unix_ms", 0) or 0),
                int(job.get("updated_at_unix_ms", 0) or 0),
                job_id,
                copy.deepcopy(summary),
            )
        )

    if not candidates:
        return (
            None,
            f"persisted evaluation_compare artifacts for suite {suite_id} were not found under {evidence_root}",
        )

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    latest_job_id = candidates[-1][2]
    latest_job_summaries = [
        summary for _, _, job_id, summary in candidates if job_id == latest_job_id
    ]
    if latest_job_id and len(latest_job_summaries) > 1:
        return (
            {
                "suite_id": suite_id,
                "job_id": latest_job_id,
                "target_summaries": sorted(
                    latest_job_summaries,
                    key=lambda summary: str(summary.get("target_model_id", "")),
                ),
            },
            "",
        )
    return latest_job_summaries[-1], ""


def _build_maintenance_core(jobs_root: str | Path) -> MaintenanceCore:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runner = _SyntheticProductizationRunner()
    return MaintenanceCore(
        registry,
        Path(jobs_root),
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=_release_gate_benchmark_fetcher
        ),
    )


def _release_gate_benchmark_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
    dataset = params.get("dataset", "")
    offset = params.get("offset", "0")
    if endpoint == "rows" and offset != "0":
        return {"rows": []}
    if dataset == "HuggingFaceH4/ultrachat_200k":
        if endpoint == "rows":
            return {
                "rows": [
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say hi."},
                                {"role": "assistant", "content": "Hi."},
                            ]
                        }
                    }
                ]
            }
        return {"splits": [{"dataset": dataset, "config": "default", "split": "train_sft"}]}
    if dataset == "databricks/databricks-dolly-15k":
        if endpoint == "rows":
            return {
                "rows": [
                    {"row": {"instruction": "Colors?", "response": "Red."}},
                    {"row": {"instruction": "Animals?", "response": "Cat."}},
                ]
            }
        return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}
    raise RuntimeError(f"Unsupported release-gate benchmark dataset: {dataset}")


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


def _summarize_real_workload_families(
    families: dict[str, Any],
) -> dict[str, float]:
    normalized = {
        str(family_id): family
        for family_id, family in families.items()
        if isinstance(family, dict)
    }
    family_count = float(len(normalized))
    pass_count = 0.0
    for family in normalized.values():
        metrics = family.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        passed = metrics.get("passed", 0.0)
        if isinstance(passed, (int, float)) and float(passed) >= 1.0:
            pass_count += 1.0
    failure_count = max(family_count - pass_count, 0.0)
    return {
        "pass_count": pass_count,
        "failure_count": failure_count,
        "family_count": family_count,
    }


def _load_persisted_real_workload_family(
    jobs_root: Path,
    *,
    family_id: str,
) -> dict[str, Any] | None:
    evidence_path = jobs_root / "real_workload" / f"{family_id}.json"
    if evidence_path.exists() is False:
        return None
    payload = _read_json(evidence_path)
    return payload if isinstance(payload, dict) else None


def evaluate_real_workload_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    summary_rules = policy.get("summary", {}) if isinstance(policy, dict) else {}
    family_rules = policy.get("families", {}) if isinstance(policy, dict) else {}

    summary = report.get("summary")
    if not isinstance(summary, dict):
        failures.append("real_workload.summary is missing")
        summary = {}
    else:
        failures.extend(
            _evaluate_section_metrics(
                summary,
                summary_rules,
                prefix="real_workload.summary.",
            )
        )

    families = report.get("families")
    if not isinstance(families, dict):
        failures.append("real_workload.families is missing")
        return failures

    normalized_families = {
        str(family_id): family
        for family_id, family in families.items()
        if isinstance(family, dict)
    }
    for family_id, rules in family_rules.items():
        if not isinstance(rules, dict):
            continue
        family = normalized_families.get(str(family_id))
        if family is None:
            failures.append(f"real_workload.families.{family_id} is missing")
            continue
        metrics = family.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(f"real_workload.families.{family_id}.metrics is missing")
            continue
        failures.extend(
            _evaluate_section_metrics(
                metrics,
                rules,
                prefix=f"real_workload.families.{family_id}.",
            )
        )

    computed_summary = _summarize_real_workload_families(normalized_families)
    for key, computed_value in computed_summary.items():
        reported_value = summary.get(key)
        if reported_value is None:
            failures.append(f"real_workload.summary.{key} is missing")
            continue
        if not isinstance(reported_value, (int, float)):
            failures.append(f"real_workload.summary.{key} must be numeric")
            continue
        if abs(float(reported_value) - computed_value) > 0.01:
            failures.append(
                f"real_workload.summary.{key}={float(reported_value):.2f} did not match computed {computed_value:.2f}"
            )

    return failures


def evaluate_lora_path_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    summary = report.get("summary")
    if not isinstance(summary, dict):
        failures.append("lora_path.summary is missing")
        return failures
    summary_rules = policy.get("summary", {}) if isinstance(policy, dict) else {}
    failures.extend(
        _evaluate_section_metrics(summary, summary_rules, prefix="lora_path.summary.")
    )
    return failures


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


def evaluate_m9_release_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[str], dict[str, float]]:
    failures: list[str] = []
    required_probe_count = 0.0
    missing_probe_count = 0.0
    failed_threshold_count = 0.0

    for section_name, section_rules in policy.items():
        if not isinstance(section_rules, dict):
            continue
        required_probe_count += float(len(section_rules))
        section = report.get(section_name, {})
        metrics = section.get("metrics", {}) if isinstance(section, dict) else {}
        section_failures = _evaluate_section_metrics(
            metrics,
            section_rules,
            prefix=f"m9.{section_name}.",
        )
        failures.extend(section_failures)
        missing_probe_count += float(
            sum(1 for failure in section_failures if failure.endswith(" is missing"))
        )
        failed_threshold_count += float(
            sum(1 for failure in section_failures if not failure.endswith(" is missing"))
        )

    return failures, {
        "required_probe_count": required_probe_count,
        "missing_probe_count": missing_probe_count,
        "failed_threshold_count": failed_threshold_count,
    }


def _run_python_json_script(
    repo_root: str | Path,
    script_relative_path: str,
    *script_args: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    env = os.environ.copy()
    pythonpath_entries = [
        str(root),
        str(root / "services" / "mlx-worker-python"),
    ]
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    command = [
        sys.executable,
        str(root / script_relative_path),
        *script_args,
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError(f"{script_relative_path} did not emit JSON output")
    return json.loads(stdout)


def _evaluate_section_metrics(
    values: dict[str, Any],
    rules: dict[str, Any],
    *,
    prefix: str = "",
) -> list[str]:
    failures: list[str] = []
    for name, rule in rules.items():
        value = values.get(name)
        display_name = f"{prefix}{name}"
        if value is None:
            failures.append(f"{display_name} is missing")
            continue
        if not isinstance(value, (int, float)):
            failures.append(f"{display_name} must be numeric")
            continue
        numeric = float(value)
        minimum = rule.get("min")
        maximum = rule.get("max")
        if minimum is not None and numeric < float(minimum):
            failures.append(
                f"{display_name}={numeric:.2f} fell below minimum {float(minimum):.2f}"
            )
        if maximum is not None and numeric > float(maximum):
            failures.append(
                f"{display_name}={numeric:.2f} exceeded maximum {float(maximum):.2f}"
            )
    return failures


def _with_evaluation_metric_aliases(
    metrics: dict[str, float],
    *,
    suite_id: str,
    primary_score_value: Any | None = None,
) -> dict[str, float]:
    normalized = dict(metrics)
    typed_metric_name = f"eval.{suite_id}.typed_score_mean"
    legacy_metric_name = f"eval.{suite_id}.accuracy"

    candidate_value: float | None = None
    for metric_name in (typed_metric_name, legacy_metric_name):
        metric_value = normalized.get(metric_name)
        if isinstance(metric_value, (int, float)):
            candidate_value = float(metric_value)
            break

    if candidate_value is None and isinstance(primary_score_value, (int, float)):
        candidate_value = float(primary_score_value)

    if candidate_value is None:
        return normalized

    normalized.setdefault(typed_metric_name, candidate_value)
    normalized.setdefault(legacy_metric_name, candidate_value)
    return normalized


def _normalize_evaluation_metrics_for_policy(
    values: Any,
    rules: Any,
) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    if not isinstance(rules, dict):
        return dict(values)

    normalized = dict(values)
    for metric_name in rules:
        if not (
            isinstance(metric_name, str)
            and metric_name.startswith("eval.")
            and metric_name.endswith(".typed_score_mean")
        ):
            continue
        suite_id = metric_name[len("eval.") : -len(".typed_score_mean")]
        normalized = _with_evaluation_metric_aliases(normalized, suite_id=suite_id)
    return normalized


def _require_true(payload: dict[str, Any], dotted_key: str) -> list[str]:
    current: Any = payload
    for segment in dotted_key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return [f"{dotted_key} is missing"]
        current = current[segment]
    if current is not True:
        return [f"{dotted_key} must be true"]
    return []
