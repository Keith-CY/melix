#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "mlx-worker-python"))

from agentic_lora_sft_smoke import DEFAULT_FIXTURE_ID, run_smoke as run_sft_smoke
from packages.protocol.python.worker.v1 import common_pb2
from worker.engine.evaluation_core import EvaluationCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.productization.evaluation_schemas import build_dataset_package_manifest
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent


DEFAULT_SUITE_ID = "agentic_tool_trace_eval"
DEFAULT_DATASET_ID = "agentic-lora-sft-smoke.eval.v1"


class _ScriptedCompareRuntime:
    runtime_name = "deterministic-agentic-lora-eval-compare"

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    def render_prompt(self, messages, loaded_model=None, execution_ext=None) -> str:
        _ = loaded_model
        _ = execution_ext
        prompt = "\n".join(
            part.text
            for message in messages
            for part in message.parts
            if part.text
        )
        self.prompts.append(prompt)
        return prompt

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = execution_ext
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(
            text=self._response,
            completion_tokens=max(1, len(self._response.split())),
        )


class _LocalCompareRegistry:
    def __init__(self) -> None:
        self._loaded_models_by_handle: dict[str, object] = {}
        self._handles_by_model_id: dict[str, str] = {}

    def register_model(self, model_spec: common_pb2.ModelSpec, runtime: _ScriptedCompareRuntime):
        handle = f"{model_spec.model_id}::agentic-eval-compare"
        loaded_model = SimpleNamespace(
            handle=handle,
            runtime_kind="text",
            runtime_model={"model_id": model_spec.model_id},
            spec=model_spec,
            runtime=runtime,
            estimated_resident_bytes=0,
        )
        self._loaded_models_by_handle[handle] = loaded_model
        self._handles_by_model_id[model_spec.model_id] = handle
        return loaded_model

    def get_loaded_model(self, handle: str):
        return self._loaded_models_by_handle.get(handle)

    def list_loaded_models(self) -> list[str]:
        return sorted(self._loaded_models_by_handle)

    def runtime_for_loaded_model(self, loaded_model):
        return loaded_model.runtime

    def start_request(self, request_id: str, runtime_kind: str = "text"):
        _ = request_id
        _ = runtime_kind
        return SimpleNamespace(cancel_event=SimpleNamespace(is_set=lambda: False))

    def finish_request(self, request_id: str) -> None:
        _ = request_id


def run_eval_compare_smoke(
    repo_root: Path,
    *,
    output_dir: Path | None = None,
    fixture_id: str = DEFAULT_FIXTURE_ID,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="melix-agentic-lora-eval-compare-"))
    else:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    training_payload = run_sft_smoke(
        repo_root,
        output_dir=output_dir / "training",
        fixture_id=fixture_id,
    )
    adapter_manifest_path = Path(training_payload["adapter_manifest_path"])
    adapter_manifest = json.loads(adapter_manifest_path.read_text(encoding="utf-8"))
    source_model = _source_model_from_adapter_manifest(adapter_manifest)

    activation_result = AdapterActivationPipeline(runner=DeterministicLoRARunner()).run(
        job_id="agentic-lora-eval-compare-activation",
        request_ext={
            "operation": "activate_adapter",
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
            "derived_model_alias": "agentic-lora-sft-smoke-activated",
        },
        source_model=source_model,
        output_dir=output_dir / "activation",
    )
    activation_manifest = activation_result.manifest

    normalized_dir = Path(training_payload["normalized_dataset_manifest_path"]).parent
    validation_trace_path = normalized_dir / "agentic-traces.valid.jsonl"
    validation_traces = _read_jsonl(validation_trace_path)
    if not validation_traces:
        raise ValueError(f"No validation traces were written: {validation_trace_path}")

    final_answer = str(validation_traces[0].get("final_answer", "")).strip()
    baseline_answer = "VX-000" if final_answer != "VX-000" else "VX-001"
    dataset_root = _write_eval_dataset_package(
        output_dir=output_dir,
        source_trace=validation_traces[0],
        source_trace_path=validation_trace_path,
    )

    activated_model_spec = _activated_model_spec_from_manifest(activation_manifest)
    registry = _LocalCompareRegistry()
    base_loaded_model = registry.register_model(
        source_model,
        _ScriptedCompareRuntime(response=f"Answer: {baseline_answer}"),
    )
    registry.register_model(
        activated_model_spec,
        _ScriptedCompareRuntime(response=f"Answer: {final_answer}"),
    )

    evaluation_root = output_dir / "evaluation"
    run = EvaluationCore(jobs_root=evaluation_root, registry=registry).run_local_suite(
        model_id=source_model.model_id,
        model_handle=base_loaded_model.handle,
        suite_id=DEFAULT_SUITE_ID,
        dataset_root=dataset_root,
        sample_size=1,
        few_shot=0,
        seed=0,
        scoring_mode="normalized_exact_match",
        code_exec_policy="disabled",
        parameters={
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": activated_model_spec.model_id,
            "adapter_manifest_path": str(adapter_manifest_path),
            "activation_manifest_path": str(activation_result.manifest_path),
            "source_training_fixture_id": fixture_id,
            "source_training_objective": "agentic_sft",
            "deterministic_evidence": "true",
        },
    )
    summary = run.results[0]
    paired_sample = run.samples[0]
    persisted_paths = {key: str(path) for key, path in run.persisted_paths.items()}

    artifacts = {
        "adapter_manifest": str(adapter_manifest_path),
        "activation_manifest": str(activation_result.manifest_path),
        "evaluation_dataset_manifest": str(dataset_root / "manifest.json"),
        "evaluation_dataset_samples": str(dataset_root / "samples.jsonl"),
        **{f"compare_{key}": value for key, value in persisted_paths.items()},
        "evidence_json": str(output_dir / "agentic-lora-eval-compare-evidence.json"),
    }
    checks = {
        "training_smoke_passed": bool(training_payload.get("passed")),
        "adapter_manifest_exists": adapter_manifest_path.is_file(),
        "activation_manifest_exists": activation_result.manifest_path.is_file(),
        "adapter_backed_activation": activation_manifest.get("activation_mode")
        == "adapter_backed_runtime",
        "compare_target_is_activated_adapter": summary.target_model_id
        == activation_manifest.get("derived_model_id")
        == activated_model_spec.model_id,
        "compare_artifacts_exist": all(
            Path(value).is_file()
            for key, value in artifacts.items()
            if key.startswith("compare_")
        ),
        "paired_sample_count": len(run.samples) == 1,
        "paired_sample_has_base_and_target": bool(
            paired_sample.base_raw_response and paired_sample.target_raw_response
        ),
        "base_sample_misses": paired_sample.base_typed_score == 0.0,
        "target_sample_matches": paired_sample.target_typed_score == 1.0,
        "target_improves_base": summary.delta_accuracy > 0.0 and summary.win_count >= 1,
        "no_regressions": summary.regression_count == 0,
    }
    duration_ms = (time.perf_counter() - started) * 1000.0
    payload = {
        "passed": all(checks.values()),
        "fixture_id": fixture_id,
        "output_dir": str(output_dir),
        "suite_id": DEFAULT_SUITE_ID,
        "dataset_id": DEFAULT_DATASET_ID,
        "duration_ms": duration_ms,
        "checks": checks,
        "artifacts": artifacts,
        "activation": {
            "derived_model_id": activation_manifest.get("derived_model_id"),
            "activation_mode": activation_manifest.get("activation_mode"),
            "activation_backend": activation_manifest.get("activation_backend"),
            "activation_duration_ms": activation_manifest.get("activation_duration_ms"),
            "adapter_set_hash": activation_manifest.get("adapter_set_hash"),
        },
        "compare": {
            "job_id": run.job.job_id,
            "base_model_id": summary.base_model_id,
            "target_model_id": summary.target_model_id,
            "base_accuracy": summary.base_accuracy,
            "target_accuracy": summary.target_accuracy,
            "delta_accuracy": summary.delta_accuracy,
            "win_count": summary.win_count,
            "loss_count": summary.loss_count,
            "tie_count": summary.tie_count,
            "regression_count": summary.regression_count,
            "verdict": summary.verdict,
        },
        "paired_sample": {
            "sample_id": paired_sample.sample_id,
            "target_model_id": paired_sample.target_model_id,
            "target": paired_sample.target,
            "base_raw_response": paired_sample.base_raw_response,
            "target_raw_response": paired_sample.target_raw_response,
            "base_extracted_result": paired_sample.base_extracted_result,
            "target_extracted_result": paired_sample.target_extracted_result,
            "base_typed_score": paired_sample.base_typed_score,
            "target_typed_score": paired_sample.target_typed_score,
            "outcome": paired_sample.outcome,
            "regression_kind": paired_sample.regression_kind,
        },
        "metrics": {
            "agentic_lora_eval_compare.base_accuracy": float(summary.base_accuracy),
            "agentic_lora_eval_compare.target_accuracy": float(summary.target_accuracy),
            "agentic_lora_eval_compare.delta_accuracy": float(summary.delta_accuracy),
            "agentic_lora_eval_compare.win_count": float(summary.win_count),
            "agentic_lora_eval_compare.loss_count": float(summary.loss_count),
            "agentic_lora_eval_compare.tie_count": float(summary.tie_count),
            "agentic_lora_eval_compare.regression_count": float(summary.regression_count),
            "agentic_lora_eval_compare.paired_sample_count": float(len(run.samples)),
            "agentic_lora_eval_compare.activated_adapter_target_count": 1.0,
            "agentic_lora_eval_compare.duration_ms": duration_ms,
        },
    }
    Path(artifacts["evidence_json"]).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _source_model_from_adapter_manifest(adapter_manifest: dict[str, Any]) -> common_pb2.ModelSpec:
    source_ext = adapter_manifest.get("source_model_ext")
    if not isinstance(source_ext, dict):
        source_ext = {
            "text_family_id": "llama",
            "text_layer_count": "1",
        }
    return common_pb2.ModelSpec(
        model_id=str(adapter_manifest.get("source_model") or "agentic-lora-sft-smoke-model"),
        model_path=str(adapter_manifest.get("source_model_path") or ""),
        revision=str(adapter_manifest.get("source_model_revision") or "fixture-v1"),
        model_kind=str(adapter_manifest.get("source_model_kind") or "text"),
        max_context=2048,
        ext={str(key): str(value) for key, value in source_ext.items()},
    )


def _activated_model_spec_from_manifest(activation_manifest: dict[str, Any]) -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id=str(activation_manifest["derived_model_id"]),
        model_path=str(activation_manifest.get("derived_model_path") or ""),
        revision=str(activation_manifest.get("source_model_revision") or "fixture-v1"),
        model_kind="text",
        max_context=2048,
        ext={
            "melix.source_kind": "adapter_backed_runtime",
            "melix.source_repo": str(activation_manifest.get("base_model_repo_id") or ""),
            "melix.adapter_manifest_path": str(activation_manifest.get("adapter_manifest_path") or ""),
            "melix.activation_manifest_path": str(activation_manifest.get("manifest_path") or ""),
        },
    )


def _write_eval_dataset_package(
    *,
    output_dir: Path,
    source_trace: dict[str, Any],
    source_trace_path: Path,
) -> Path:
    dataset_root = output_dir / "evaluation-dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)
    manifest = build_dataset_package_manifest(
        dataset_id=DEFAULT_DATASET_ID,
        suite_id=DEFAULT_SUITE_ID,
        version="dev.v1",
        sample_count=1,
        split="validation",
        task_kind="text-generation",
        input_modalities=("text",),
        profile_type="final_result",
        result_kind="text",
        extraction_mode="heuristic_final",
        scoring_mode="normalized_exact_match",
        threshold=1.0,
        source_kind="agentic_tool_trace",
        source_path=str(source_trace_path),
    ).to_dict()
    manifest.update(
        {
            "trajectory_schema_version": source_trace.get(
                "trajectory_schema_version",
                "melix.agentic_tool_trace.v1",
            ),
            "source_trace_id": str(source_trace.get("trace_id") or ""),
        }
    )
    (dataset_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sample = {
        "id": str(source_trace.get("trace_id") or "agentic-lora-eval-compare-1"),
        "system": "Use the agentic tool trace evidence and return only the final short answer.",
        "input": {"text": _prompt_from_trace(source_trace)},
        "target": str(source_trace.get("final_answer") or source_trace.get("expected_answer") or ""),
        "category": "agentic_tool_trace",
        "subject": "activated_adapter_compare",
        "source_trace_id": str(source_trace.get("trace_id") or ""),
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
    }
    _write_jsonl(dataset_root / "samples.jsonl", (sample,))
    return dataset_root


def _prompt_from_trace(source_trace: dict[str, Any]) -> str:
    observations: list[str] = []
    for turn in source_trace.get("turns", []):
        if not isinstance(turn, dict) or turn.get("role") != "tool":
            continue
        observation = turn.get("observation")
        if isinstance(observation, dict):
            text = str(observation.get("text") or "").strip()
        else:
            text = str(observation or "").strip()
        if text:
            observations.append(f"- {text}")
    evidence = "\n".join(observations) if observations else "- No tool observation recorded."
    return (
        f"{source_trace.get('question', '')}\n\n"
        f"Agentic tool observations:\n{evidence}\n\n"
        "Answer with only the final short answer."
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic agentic LoRA eval compare smoke evidence."
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable payload.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the script parent repository.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for persisted smoke artifacts. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--fixture-id",
        default=DEFAULT_FIXTURE_ID,
        help="Training fixture id under services/mlx-worker-python/fixtures/training.",
    )
    args = parser.parse_args()

    payload = run_eval_compare_smoke(
        args.repo_root,
        output_dir=args.output_dir,
        fixture_id=args.fixture_id,
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(
            "Agentic LoRA eval compare smoke passed."
            if payload["passed"]
            else "Agentic LoRA eval compare smoke failed."
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
