#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, Sequence


ISSUE_URL = "https://github.com/Keith-CY/melix/issues/365"
BUNDLE_SCHEMA_VERSION = "melix.issue365.acceptance_bundle.v1"
PIPELINE_SCHEMA_VERSION = "melix.pipeline.v1"


@dataclass(frozen=True, slots=True)
class Issue365AcceptanceConfig:
    repo_root: Path
    output_dir: Path
    execution_mode: str = "plan"
    model_id: str = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    sft_dataset_uri: str = "/tmp/melix-issue365/datasets/sft"
    preference_dataset_uri: str = "/tmp/melix-issue365/datasets/preference_pair"
    prompt_candidate_dataset_uri: str = "/tmp/melix-issue365/datasets/prompt_candidate"
    reward_scored_dataset_uri: str = "/tmp/melix-issue365/datasets/reward_scored"
    calibration_dataset_uri: str = "/tmp/melix-issue365/datasets/calibration"
    reward_model_manifest_path: str = "/tmp/melix-issue365/reward-model/manifest.json"
    melix_cli: str = "melix"
    case_ids: tuple[str, ...] = ()
    timestamp: str = ""
    json_output: bool = False


@dataclass(frozen=True, slots=True)
class Issue365PipelineCase:
    case_id: str
    requirement: str
    business_line: str
    steps: tuple[dict[str, Any], ...]
    acceptance_requirements: tuple[str, ...]
    required_inputs: tuple[str, ...] = ()


class JSONCommandExecutor(Protocol):
    def run_json(self, command: Sequence[str]) -> dict[str, Any]:
        ...


class SubprocessJSONExecutor:
    def __init__(self, *, repo_root: Path, environment: dict[str, str] | None = None) -> None:
        self.repo_root = repo_root
        self.environment = dict(os.environ if environment is None else environment)

    def run_json(self, command: Sequence[str]) -> dict[str, Any]:
        completed = subprocess.run(
            list(command),
            cwd=self.repo_root,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{' '.join(command)} failed with exit code {completed.returncode}: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{' '.join(command)} did not return JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{' '.join(command)} returned non-object JSON.")
        return payload


def build_acceptance_bundle(
    config: Issue365AcceptanceConfig,
    *,
    executor: JSONCommandExecutor | None = None,
) -> dict[str, Any]:
    if config.execution_mode not in {"plan", "dry-run", "real"}:
        raise ValueError("execution_mode must be plan, dry-run, or real")

    timestamp = config.timestamp or _utc_timestamp()
    output_dir = config.output_dir.resolve()
    pipeline_dir = output_dir / "pipelines"
    receipt_root = output_dir / "receipts"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    receipt_root.mkdir(parents=True, exist_ok=True)

    inputs = _default_inputs(config, output_dir=output_dir)
    cases = _selected_pipeline_cases(config.case_ids)
    real_runtime_preflight = _real_runtime_preflight(config, cases) if config.execution_mode == "real" else {
        "status": "not_run",
        "ready": False,
        "reason": "Real local runtime preflight only runs in execution_mode=real.",
        "cases": {},
    }
    case_results: list[dict[str, Any]] = []
    runner = executor
    if config.execution_mode != "plan" and runner is None:
        runner = SubprocessJSONExecutor(repo_root=config.repo_root)

    for case in cases:
        pipeline_path = pipeline_dir / f"{case.case_id}.pipeline.json"
        pipeline = {
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "name": f"issue365-{case.case_id}",
            "inputs": inputs,
            "steps": list(case.steps),
        }
        _write_json(pipeline_path, pipeline)

        command = _pipeline_command(
            config,
            pipeline_path=pipeline_path,
            receipt_dir=receipt_root / case.case_id,
            trace_id=f"issue365-{case.case_id}-{timestamp}",
        )
        summary: dict[str, Any] | None = None
        status = "planned"
        error = ""
        case_preflight = real_runtime_preflight.get("cases", {}).get(case.case_id)
        if config.execution_mode == "real" and case_preflight is not None and not case_preflight["ready"]:
            status = "blocked"
            error = "Real local runtime preflight failed."
        elif config.execution_mode != "plan":
            try:
                assert runner is not None
                summary = runner.run_json(command)
                status = str(summary.get("status", "unknown"))
            except Exception as exc:  # pragma: no cover - subprocess path is covered via fake executor.
                status = "failed"
                error = str(exc)

        case_results.append(
            _case_result(
                case,
                execution_mode=config.execution_mode,
                pipeline_path=pipeline_path,
                command=command,
                status=status,
                summary=summary,
                error=error,
                real_runtime_preflight=case_preflight,
            )
        )

    summary = _bundle_summary(case_results, execution_mode=config.execution_mode)
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "generated_at": timestamp,
        "execution_mode": config.execution_mode,
        "release_ready": summary["release_ready"],
        "evidence_policy": {
            "unit_and_plan_evidence_release_ready": False,
            "deterministic_dry_run_release_ready": False,
            "real_local_runtime_required": True,
            "real_local_runtime_preflight_required": True,
        },
        "inputs": inputs,
        "selected_case_ids": [case.case_id for case in cases],
        "real_runtime_preflight": real_runtime_preflight,
        "summary": summary,
        "cases": case_results,
        "known_gaps": _known_gaps(case_results, execution_mode=config.execution_mode),
    }
    bundle_path = output_dir / "bundle.json"
    _write_json(bundle_path, bundle)
    bundle["bundle_path"] = str(bundle_path)
    _write_json(bundle_path, bundle)
    return bundle


def issue365_pipeline_cases() -> tuple[Issue365PipelineCase, ...]:
    return (
        _supervised_case("lora"),
        _supervised_case("qlora"),
        _supervised_case("dora"),
        _alignment_case("dpo", "${inputs.preference_dataset_uri}"),
        _alignment_case("orpo", "${inputs.preference_dataset_uri}"),
        _alignment_case("cpo", "${inputs.preference_dataset_uri}"),
        _alignment_case(
            "grpo",
            "${inputs.prompt_candidate_dataset_uri}",
            extra_alignment_args={
                "grpo_candidate_count": 4,
                "candidate_generation_mode": "runtime_generate",
                "candidate_scoring_mode": "reward_model",
                "candidate_generation_max_tokens": 16,
                "reward_model_manifest_path": "${inputs.reward_model_manifest_path}",
            },
            requirement="BaseModel -> LoRA -> GRPO -> export -> local inference.",
        ),
        _alignment_case(
            "rlhf",
            "${inputs.reward_scored_dataset_uri}",
            extra_alignment_args={"reward_model_manifest_path": "${inputs.reward_model_manifest_path}"},
            requirement="BaseModel -> LoRA -> RLHF using a reward model from #366 -> export -> local inference.",
        ),
        _ptq_case(),
        _qat_case(),
    )


def _supervised_case(training_mode: str) -> Issue365PipelineCase:
    case_id = f"{training_mode}_export_inference"
    train_step = f"{training_mode}_train"
    publish_step = f"{training_mode}_publish"
    activate_step = f"{training_mode}_activate"
    derived_alias = f"issue365-{training_mode}-derived"
    return Issue365PipelineCase(
        case_id=case_id,
        requirement=f"BaseModel -> {training_mode.upper()} -> export -> local inference.",
        business_line="supervised_adapter_training",
        acceptance_requirements=(
            "adapter training completed",
            "export or publish artifact exists",
            "local inference smoke completed",
            "evaluation evidence recorded",
            "real local runtime evidence captured",
        ),
        required_inputs=("sft_dataset_uri",),
        steps=(
            {
                "id": train_step,
                "command": "lora.train",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "dataset_uri": "${inputs.sft_dataset_uri}",
                    "adapter_name": f"issue365-{training_mode}",
                    "training_mode": training_mode,
                    "preset_id": "debug_fast",
                    "max_steps": 2,
                },
            },
            {
                "id": publish_step,
                "command": "lora.publish",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "target_repo": f"melix/issue365-{training_mode}-adapter",
                    "adapter_path": f"${{steps.{train_step}.result.output_path}}",
                    "publish_backend": "local_filesystem",
                    "local_publish_root": "${inputs.local_publish_root}",
                },
            },
            {
                "id": activate_step,
                "command": "lora.activate",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "adapter_path": f"${{steps.{train_step}.result.output_path}}",
                    "derived_model_alias": derived_alias,
                    "activation_mode": "adapter_backed_runtime",
                },
            },
            _chat_step(f"{training_mode}_chat", f"${{steps.{activate_step}.result.derived_model_id}}"),
            _eval_step(f"{training_mode}_eval", f"${{steps.{activate_step}.result.derived_model_id}}"),
        ),
    )


def _alignment_case(
    algorithm: str,
    dataset_uri: str,
    *,
    extra_alignment_args: dict[str, Any] | None = None,
    requirement: str | None = None,
) -> Issue365PipelineCase:
    train_step = f"{algorithm}_base_lora"
    align_step = f"{algorithm}_align"
    publish_step = f"{algorithm}_publish"
    activate_step = f"{algorithm}_activate"
    derived_alias = f"issue365-{algorithm}-derived"
    alignment_args: dict[str, Any] = {
        "model_id": "${inputs.model_id}",
        "dataset_uri": dataset_uri,
        "adapter_name": f"issue365-{algorithm}",
        "algorithm": algorithm,
        "source_adapter_path": f"${{steps.{train_step}.result.output_path}}",
        "preset_id": "debug_fast",
        "max_steps": 2,
    }
    if extra_alignment_args:
        alignment_args.update(extra_alignment_args)
    return Issue365PipelineCase(
        case_id=f"lora_{algorithm}_export_inference",
        requirement=requirement or f"BaseModel -> LoRA -> {algorithm.upper()} -> export -> local inference.",
        business_line="alignment_training",
        acceptance_requirements=(
            "base adapter training completed",
            f"{algorithm} alignment run completed",
            "alignment_run manifest exists",
            "export or publish artifact exists",
            "local inference smoke completed",
            "evaluation evidence recorded",
            "real local runtime evidence captured",
        ),
        required_inputs=_alignment_required_inputs(algorithm),
        steps=(
            {
                "id": train_step,
                "command": "lora.train",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "dataset_uri": "${inputs.sft_dataset_uri}",
                    "adapter_name": f"issue365-{algorithm}-base",
                    "training_mode": "lora",
                    "preset_id": "debug_fast",
                    "max_steps": 2,
                },
            },
            {
                "id": align_step,
                "command": "alignment.train",
                "args": alignment_args,
            },
            {
                "id": publish_step,
                "command": "lora.publish",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "target_repo": f"melix/issue365-{algorithm}-aligned",
                    "adapter_path": f"${{steps.{align_step}.result.output_path}}",
                    "publish_backend": "local_filesystem",
                    "local_publish_root": "${inputs.local_publish_root}",
                },
            },
            {
                "id": activate_step,
                "command": "lora.activate",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "adapter_path": f"${{steps.{align_step}.result.output_path}}",
                    "derived_model_alias": derived_alias,
                    "activation_mode": "adapter_backed_runtime",
                },
            },
            _chat_step(f"{algorithm}_chat", f"${{steps.{activate_step}.result.derived_model_id}}"),
            _eval_step(f"{algorithm}_eval", f"${{steps.{activate_step}.result.derived_model_id}}"),
        ),
    )


def _ptq_case() -> Issue365PipelineCase:
    train_step = "ptq_base_lora"
    align_step = "ptq_dpo_align"
    fuse_step = "ptq_fuse_merged_model"
    publish_step = "ptq_publish_export"
    quantize_step = "ptq_quantize"
    return Issue365PipelineCase(
        case_id="lora_preference_ptq_quantized_inference",
        requirement="BaseModel -> LoRA/preference result -> merge/export -> PTQ -> local inference.",
        business_line="quantization_optimization",
        acceptance_requirements=(
            "base adapter training completed",
            "preference alignment completed",
            "merged or exported artifact exists",
            "fused derived model exists for MLX-LM conversion",
            "PTQ quantization completed",
            "quantized local inference smoke completed",
            "quality and latency evidence recorded",
            "real local runtime evidence captured",
        ),
        required_inputs=("sft_dataset_uri", "preference_dataset_uri", "calibration_dataset_uri"),
        steps=(
            {
                "id": train_step,
                "command": "lora.train",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "dataset_uri": "${inputs.sft_dataset_uri}",
                    "adapter_name": "issue365-ptq-base",
                    "training_mode": "lora",
                    "preset_id": "debug_fast",
                    "max_steps": 2,
                },
            },
            {
                "id": align_step,
                "command": "alignment.train",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "dataset_uri": "${inputs.preference_dataset_uri}",
                    "adapter_name": "issue365-ptq-dpo",
                    "algorithm": "dpo",
                    "source_adapter_path": f"${{steps.{train_step}.result.output_path}}",
                    "preset_id": "debug_fast",
                    "max_steps": 2,
                },
            },
            {
                "id": fuse_step,
                "command": "lora.activate",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "adapter_path": f"${{steps.{align_step}.result.output_path}}",
                    "derived_model_alias": "issue365-ptq-merged",
                    "activation_mode": "fused_derived_model",
                },
                "checks": {"required_result_fields": ["derived_model_path"]},
            },
            {
                "id": publish_step,
                "command": "lora.publish",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "target_repo": "melix/issue365-ptq-export",
                    "merged_model_path": f"${{steps.{fuse_step}.result.derived_model_path}}",
                    "export_kind": "merged",
                    "publish_backend": "local_filesystem",
                    "local_publish_root": "${inputs.local_publish_root}",
                },
            },
            {
                "id": quantize_step,
                "command": "quantize",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "output_dir": "${inputs.acceptance_output_dir}/ptq",
                    "quant_profile_id": "q4",
                    "weight_quant": "q4",
                    "kv_quant": "q8",
                    "quantization_mode": "ptq",
                    "source_artifact_kind": "merged_adapter",
                    "source_artifact_path": f"${{steps.{publish_step}.result.output_path}}",
                    "quantization_backend": "mlx_lm_convert",
                    "mlx_lm_q_mode": "affine",
                    "calibration_dataset_uri": "${inputs.calibration_dataset_uri}",
                    "quality_delta": 0,
                    "latency_delta": 0,
                    "local_inference_smoke_mode": "runtime_generate",
                    "local_inference_smoke_prompt": "Reply with ISSUE365_OK",
                },
                "checks": _quantized_runtime_smoke_checks(),
            },
        ),
    )


def _qat_case() -> Issue365PipelineCase:
    train_step = "qat_train"
    fuse_step = "qat_fuse_merged_model"
    publish_step = "qat_publish_export"
    quantize_step = "qat_quantize"
    return Issue365PipelineCase(
        case_id="qat_quantized_inference",
        requirement="BaseModel -> QAT/QAT-aware export -> quantized local inference.",
        business_line="quantization_optimization",
        acceptance_requirements=(
            "QAT or QAT-aware training/export completed",
            "fake-quant or quantization-aware settings recorded",
            "QAT quantized export completed",
            "quantized local inference smoke completed",
            "quality and latency evidence recorded",
            "real local runtime evidence captured",
        ),
        required_inputs=("sft_dataset_uri", "calibration_dataset_uri"),
        steps=(
            {
                "id": train_step,
                "command": "lora.train",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "dataset_uri": "${inputs.sft_dataset_uri}",
                    "adapter_name": "issue365-qat-aware",
                    "training_mode": "qlora",
                    "preset_id": "debug_fast",
                    "max_steps": 2,
                    "total_layers": 2,
                    "num_layers": 2,
                    "qat_fake_quant": "enabled",
                },
            },
            {
                "id": fuse_step,
                "command": "lora.activate",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "adapter_path": f"${{steps.{train_step}.result.output_path}}",
                    "derived_model_alias": "issue365-qat-merged",
                    "activation_mode": "fused_derived_model",
                },
                "checks": {"required_result_fields": ["derived_model_path"]},
            },
            {
                "id": publish_step,
                "command": "lora.publish",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "target_repo": "melix/issue365-qat-export",
                    "merged_model_path": f"${{steps.{fuse_step}.result.derived_model_path}}",
                    "export_kind": "merged",
                    "publish_backend": "local_filesystem",
                    "local_publish_root": "${inputs.local_publish_root}",
                },
            },
            {
                "id": quantize_step,
                "command": "quantize",
                "args": {
                    "model_id": "${inputs.model_id}",
                    "output_dir": "${inputs.acceptance_output_dir}/qat",
                    "quant_profile_id": "q4",
                    "weight_quant": "q4",
                    "kv_quant": "q8",
                    "quantization_mode": "qat",
                    "source_artifact_kind": "merged_adapter",
                    "source_artifact_path": f"${{steps.{publish_step}.result.output_path}}",
                    "quantization_backend": "mlx_lm_convert",
                    "mlx_lm_q_mode": "affine",
                    "calibration_dataset_uri": "${inputs.calibration_dataset_uri}",
                    "quality_delta": 0,
                    "latency_delta": 0,
                    "qat_fake_quant": "enabled",
                    "local_inference_smoke_mode": "runtime_generate",
                    "local_inference_smoke_prompt": "Reply with ISSUE365_OK",
                },
                "checks": _quantized_runtime_smoke_checks(),
            },
        ),
    )


def _quantized_runtime_smoke_checks() -> dict[str, Any]:
    return {
        "required_result_fields": [
            "job_id",
            "output_path",
            "artifact_path",
            "local_inference_smoke.status",
            "release_gate.local_inference_smoke_result",
        ],
        "equals": {
            "result.local_inference_smoke.status": "passed",
            "result.local_inference_smoke.evidence_kind": "local_runtime_generate",
            "result.local_inference_smoke.smoke_mode": "runtime_generate",
            "result.release_gate.local_inference_smoke_result": "passed",
        },
    }


def _chat_step(step_id: str, model_id: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "command": "chat.run",
        "args": {
            "model_id": model_id,
            "message": "Reply with ISSUE365_OK",
            "server_session_id": "${inputs.server_session_id}",
        },
    }


def _eval_step(step_id: str, model_id: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "command": "eval.run",
        "args": {
            "model_id": model_id,
            "suites": ["mmlu"],
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 1,
            "scoring_mode": "multiple_choice_accuracy",
        },
    }


def _alignment_required_inputs(algorithm: str) -> tuple[str, ...]:
    if algorithm in {"dpo", "orpo", "cpo"}:
        return ("sft_dataset_uri", "preference_dataset_uri")
    if algorithm == "grpo":
        return ("sft_dataset_uri", "prompt_candidate_dataset_uri", "reward_model_manifest_path")
    if algorithm == "rlhf":
        return ("sft_dataset_uri", "reward_scored_dataset_uri", "reward_model_manifest_path")
    raise ValueError(f"Unsupported alignment algorithm: {algorithm}")


def _default_inputs(config: Issue365AcceptanceConfig, *, output_dir: Path) -> dict[str, Any]:
    return {
        "model_id": config.model_id,
        "sft_dataset_uri": config.sft_dataset_uri,
        "preference_dataset_uri": config.preference_dataset_uri,
        "prompt_candidate_dataset_uri": config.prompt_candidate_dataset_uri,
        "reward_scored_dataset_uri": config.reward_scored_dataset_uri,
        "calibration_dataset_uri": config.calibration_dataset_uri,
        "reward_model_manifest_path": config.reward_model_manifest_path,
        "acceptance_output_dir": str(output_dir / "artifacts"),
        "local_publish_root": str(output_dir / "artifacts" / "local-publish"),
        "server_session_id": "issue365-acceptance",
    }


def _selected_pipeline_cases(case_ids: tuple[str, ...]) -> tuple[Issue365PipelineCase, ...]:
    cases = issue365_pipeline_cases()
    if not case_ids:
        return cases
    case_by_id = {case.case_id: case for case in cases}
    unknown = sorted(set(case_ids) - set(case_by_id))
    if unknown:
        raise ValueError(f"Unknown Issue 365 case_id(s): {', '.join(unknown)}")
    return tuple(case_by_id[case_id] for case_id in case_ids)


def _real_runtime_preflight(
    config: Issue365AcceptanceConfig,
    cases: tuple[Issue365PipelineCase, ...],
) -> dict[str, Any]:
    common_checks = [
        _repo_root_check(config.repo_root),
        _cli_executable_check(config.melix_cli, repo_root=config.repo_root),
    ]
    input_checks = _input_preflight_checks(config)
    case_results: dict[str, Any] = {}
    for case in cases:
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for check in common_checks:
            if check["ready"]:
                if check.get("warning"):
                    warnings.append(check)
            else:
                blockers.append(check)
        required_input_checks = []
        for input_name in case.required_inputs:
            input_check = input_checks[input_name]
            required_input_checks.append(input_check)
            if input_check["ready"]:
                if input_check.get("warning"):
                    warnings.append(input_check)
            else:
                blockers.append(input_check)
        case_results[case.case_id] = {
            "ready": not blockers,
            "required_inputs": list(case.required_inputs),
            "blockers": blockers,
            "warnings": warnings,
            "checks": {
                "common": common_checks,
                "inputs": required_input_checks,
            },
        }
    ready = all(case["ready"] for case in case_results.values())
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "checked_case_count": len(case_results),
        "common_checks": common_checks,
        "cases": case_results,
    }


def _repo_root_check(repo_root: Path) -> dict[str, Any]:
    return _preflight_check(
        code="repo_root_missing",
        label="repo_root",
        value=str(repo_root),
        ready=repo_root.exists() and repo_root.is_dir(),
        detail="Repository root must exist before real local runtime execution.",
    )


def _cli_executable_check(melix_cli: str, *, repo_root: Path) -> dict[str, Any]:
    resolved = _resolve_cli_path(melix_cli, repo_root=repo_root)
    ready = resolved is not None and resolved.exists() and os.access(resolved, os.X_OK)
    return _preflight_check(
        code="melix_cli_not_executable",
        label="melix_cli",
        value=melix_cli,
        ready=ready,
        detail="Real local runtime execution requires an executable melix CLI path.",
        resolved_path=str(resolved) if resolved is not None else "",
    )


def _resolve_cli_path(melix_cli: str, *, repo_root: Path) -> Path | None:
    if "/" in melix_cli:
        path = Path(melix_cli).expanduser()
        return path if path.is_absolute() else (repo_root / path).resolve()
    resolved = shutil.which(melix_cli)
    return Path(resolved) if resolved else None


def _input_preflight_checks(config: Issue365AcceptanceConfig) -> dict[str, dict[str, Any]]:
    values = {
        "sft_dataset_uri": config.sft_dataset_uri,
        "preference_dataset_uri": config.preference_dataset_uri,
        "prompt_candidate_dataset_uri": config.prompt_candidate_dataset_uri,
        "reward_scored_dataset_uri": config.reward_scored_dataset_uri,
        "calibration_dataset_uri": config.calibration_dataset_uri,
        "reward_model_manifest_path": config.reward_model_manifest_path,
    }
    return {
        name: _input_uri_check(
            name,
            value,
            require_file=name == "reward_model_manifest_path",
            repo_root=config.repo_root,
        )
        for name, value in values.items()
    }


def _input_uri_check(name: str, value: str, *, require_file: bool, repo_root: Path) -> dict[str, Any]:
    if not value.strip():
        return _preflight_check(
            code=f"empty_{name}",
            label=name,
            value=value,
            ready=False,
            detail="Real local runtime execution requires a non-empty input value before running the case.",
        )
    local_path = _local_uri_path(value, repo_root=repo_root)
    if local_path is None:
        return _preflight_check(
            code="non_local_input_not_checked",
            label=name,
            value=value,
            ready=True,
            detail="Input is not a local path, so the acceptance bundle cannot preflight its contents.",
            warning=True,
        )
    ready = local_path.exists() and (local_path.is_file() if require_file else True)
    expected = "file" if require_file else "path"
    return _preflight_check(
        code=f"missing_{name}",
        label=name,
        value=value,
        ready=ready,
        detail=f"Real local runtime execution requires this {expected} before running the case.",
        resolved_path=str(local_path),
    )


def _local_uri_path(value: str, *, repo_root: Path) -> Path | None:
    if value.startswith("file://"):
        return Path(value.removeprefix("file://")).expanduser()
    if "://" in value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (repo_root / path).resolve()


def _preflight_check(
    *,
    code: str,
    label: str,
    value: str,
    ready: bool,
    detail: str,
    resolved_path: str = "",
    warning: bool = False,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "label": label,
        "value": value,
        "ready": ready,
        "detail": detail,
    }
    if resolved_path:
        payload["resolved_path"] = resolved_path
    if warning:
        payload["warning"] = True
    return payload


def _pipeline_command(
    config: Issue365AcceptanceConfig,
    *,
    pipeline_path: Path,
    receipt_dir: Path,
    trace_id: str,
) -> list[str]:
    command = [
        config.melix_cli,
        "pipeline",
        "run",
        "--file",
        str(pipeline_path),
        "--receipt-dir",
        str(receipt_dir),
        "--trace-id",
        trace_id,
        "--format",
        "json-v1",
    ]
    if config.execution_mode == "dry-run":
        command.append("--dry-run")
    return command


def _case_result(
    case: Issue365PipelineCase,
    *,
    execution_mode: str,
    pipeline_path: Path,
    command: Sequence[str],
    status: str,
    summary: dict[str, Any] | None,
    error: str,
    real_runtime_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence_tier = {
        "plan": "planning_matrix",
        "dry-run": "deterministic_dry_run",
        "real": "real_local_runtime",
    }[execution_mode]
    release_ready = execution_mode == "real" and status == "succeeded"
    result = {
        "case_id": case.case_id,
        "requirement": case.requirement,
        "business_line": case.business_line,
        "status": status,
        "evidence_tier": evidence_tier,
        "release_ready": release_ready,
        "real_local_runtime_required": True,
        "pipeline_path": str(pipeline_path),
        "command": list(command),
        "acceptance_requirements": list(case.acceptance_requirements),
        "step_ids": [str(step["id"]) for step in case.steps],
        "commands": [str(step["command"]) for step in case.steps],
        "missing_evidence": [] if release_ready else _missing_evidence(execution_mode, status),
    }
    if real_runtime_preflight is not None:
        result["real_runtime_preflight"] = real_runtime_preflight
    if summary is not None:
        result["pipeline_summary"] = summary
        if summary.get("summary_path"):
            result["summary_path"] = summary["summary_path"]
    if error:
        result["error"] = error
    return result


def _missing_evidence(execution_mode: str, status: str) -> list[str]:
    missing = []
    if status != "succeeded" or execution_mode != "real":
        missing.append("real_local_runtime_pipeline_success")
    if execution_mode == "plan":
        missing.append("pipeline_execution")
    if execution_mode == "dry-run":
        missing.append("non_dry_run_execution")
    if status == "blocked":
        missing.append("real_local_runtime_preflight")
    if status == "failed":
        missing.append("passing_pipeline_summary")
    return missing


def _bundle_summary(case_results: list[dict[str, Any]], *, execution_mode: str) -> dict[str, Any]:
    total = len(case_results)
    succeeded = sum(1 for case in case_results if case["status"] == "succeeded")
    planned = sum(1 for case in case_results if case["status"] == "planned")
    failed = sum(1 for case in case_results if case["status"] == "failed")
    blocked = sum(1 for case in case_results if case["status"] == "blocked")
    release_ready_cases = sum(1 for case in case_results if case["release_ready"] is True)
    release_ready = execution_mode == "real" and release_ready_cases == total and total > 0
    return {
        "case_count": total,
        "planned_count": planned,
        "succeeded_count": succeeded,
        "failed_count": failed,
        "blocked_count": blocked,
        "release_ready_case_count": release_ready_cases,
        "release_ready": release_ready,
        "required_case_ids": [case["case_id"] for case in case_results],
    }


def _known_gaps(case_results: list[dict[str, Any]], *, execution_mode: str) -> list[str]:
    if execution_mode == "real" and all(case["release_ready"] is True for case in case_results):
        return []
    gaps = [
        "Issue 365 is not release-ready until every case has real_local_runtime evidence.",
        "Plan-only and deterministic dry-run evidence are regression coverage, not final acceptance.",
    ]
    missing = sorted(
        {
            item
            for case in case_results
            for item in case.get("missing_evidence", [])
        }
    )
    gaps.extend(missing)
    return gaps


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write or run the Issue 365 CLI acceptance matrix bundle."
    )
    parser.add_argument(
        "--execution-mode",
        choices=("plan", "dry-run", "real"),
        default="plan",
        help="plan writes matrix files only; dry-run invokes melix pipeline run --dry-run; real invokes the pipelines.",
    )
    parser.add_argument("--output-dir", default=".runtime/issue365/acceptance")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--melix-cli", default="melix")
    parser.add_argument("--model-id", default="mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    parser.add_argument("--sft-dataset-uri", default="/tmp/melix-issue365/datasets/sft")
    parser.add_argument("--preference-dataset-uri", default="/tmp/melix-issue365/datasets/preference_pair")
    parser.add_argument("--prompt-candidate-dataset-uri", default="/tmp/melix-issue365/datasets/prompt_candidate")
    parser.add_argument("--reward-scored-dataset-uri", default="/tmp/melix-issue365/datasets/reward_scored")
    parser.add_argument("--calibration-dataset-uri", default="/tmp/melix-issue365/datasets/calibration")
    parser.add_argument("--reward-model-manifest-path", default="/tmp/melix-issue365/reward-model/manifest.json")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only the selected Issue 365 acceptance case. May be repeated.",
    )
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config = Issue365AcceptanceConfig(
        repo_root=Path(args.repo_root),
        output_dir=Path(args.output_dir),
        execution_mode=args.execution_mode,
        model_id=args.model_id,
        sft_dataset_uri=args.sft_dataset_uri,
        preference_dataset_uri=args.preference_dataset_uri,
        prompt_candidate_dataset_uri=args.prompt_candidate_dataset_uri,
        reward_scored_dataset_uri=args.reward_scored_dataset_uri,
        calibration_dataset_uri=args.calibration_dataset_uri,
        reward_model_manifest_path=args.reward_model_manifest_path,
        melix_cli=args.melix_cli,
        case_ids=tuple(args.case_id),
        timestamp=args.timestamp,
        json_output=args.json,
    )
    bundle = build_acceptance_bundle(config)
    if args.json:
        print(json.dumps(bundle, indent=2, sort_keys=True))
    else:
        print(bundle["bundle_path"])
        print(f"release_ready={str(bundle['release_ready']).lower()}")
        print(f"execution_mode={bundle['execution_mode']}")
    return 0 if bundle["release_ready"] or args.execution_mode != "real" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
