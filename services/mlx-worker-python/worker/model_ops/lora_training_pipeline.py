from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.multimodal_lora_contracts import (
    audit_adapter_checkpoint,
    audit_manifest_fields,
    raise_for_adapter_freeze_audit,
)
from worker.model_ops.response_only_boundary import ResponseOnlyBoundaryAggregate
from worker.model_ops.mlx_lm_runner import MLXLMRunner, TrainingRequest, TrainingResult
from worker.model_ops.training_config import LoRATrainingConfig, normalize_training_config
from worker.model_ops.training_dataset import (
    HFDatasetFetcher,
    ResolvedTrainingDatasetPackage,
    resolve_training_dataset_package,
    write_normalized_dataset_snapshot,
)
from worker.productization.lora_experiment_store import LoraExperimentStore


_NUMERIC_TOKEN_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class LoRATrainingPipelineResult:
    manifest: dict[str, Any]
    manifest_path: Path


class LoRATrainingPipeline:
    def __init__(
        self,
        runner: MLXLMRunner | None = None,
        policy_runtime: Any | None = None,
        reward_runtime: Any | None = None,
        hf_dataset_fetcher: HFDatasetFetcher | None = None,
        experiment_store: LoraExperimentStore | None = None,
    ) -> None:
        self._runner = runner or MLXLMRunner(policy_runtime=policy_runtime, reward_runtime=reward_runtime)
        self._hf_dataset_fetcher = hf_dataset_fetcher
        self._experiment_store = experiment_store or LoraExperimentStore()

    def run(
        self,
        *,
        job_id: str,
        request_ext: dict[str, str],
        source_model: common_pb2.ModelSpec,
        output_dir: Path,
        jobs_root: Path,
        progress: Callable[[str, float], None] | None = None,
    ) -> LoRATrainingPipelineResult:
        emit = progress or (lambda stage, pct: None)

        emit("resolve_source", 0.1)
        emit("validate_dataset", 0.2)
        dataset = resolve_training_dataset_package(
            request_ext,
            jobs_root=jobs_root,
            hf_dataset_fetcher=self._hf_dataset_fetcher,
            sample_limit=_int_ext(request_ext, "sample_limit"),
            max_characters_per_sample=_int_ext(request_ext, "max_characters_per_sample"),
        )

        emit("normalize_config", 0.35)
        config = normalize_training_config(
            source_model=source_model,
            ext=request_ext,
            dataset_format=dataset.package.format,
            response_only_supported=dataset.package.response_only_supported,
            sample_count=dataset.package.sample_count,
            validation_sample_count=dataset.package.validation_sample_count,
        )
        _validate_alignment_inputs(
            config=config,
            samples=dataset.package.normalized_samples,
        )

        emit("prepare_training_data", 0.5)
        normalized_manifest_overrides: dict[str, Any] = {
            "validation_strategy": config.validation_strategy,
            "validation_sample_count": config.validation_sample_count,
        }
        if config.validation_split:
            normalized_manifest_overrides["hf_valid_split"] = config.validation_split
        normalized_snapshot = write_normalized_dataset_snapshot(
            dataset.package,
            output_dir=output_dir,
            manifest_overrides=normalized_manifest_overrides,
        )

        emit("apply_lora", 0.65)
        adapter_output_dir = output_dir / "adapter"
        resume_context = _resolve_resume_context(request_ext)
        adapter_scope = _resolve_adapter_scope_metadata(source_model)
        training_model_path = Path(adapter_scope["component_model_path"]).expanduser()

        emit("train", 0.8)
        training_result = self._runner.train(
            TrainingRequest(
                job_id=job_id,
                base_model_id=source_model.model_id,
                model_path=training_model_path,
                model_revision=source_model.revision,
                adapter_output_dir=adapter_output_dir,
                normalized_dataset_dir=normalized_snapshot.dataset_dir,
                config=config,
                dataset_format=dataset.package.format,
                resume_source_path=resume_context["resume_source_path"],
                source_model_kind=source_model.model_kind,
                source_model_ext=dict(source_model.ext),
            )
        )

        emit("write_adapter", 0.9)
        adapter_audit = audit_adapter_checkpoint(
            weights_path=training_result.weights_path,
            allowed_target_modules=config.expanded_target_modules,
            source_model_kind=source_model.model_kind,
            source_model_ext=dict(source_model.ext),
            live_audit=training_result.metrics.adapter_freeze_audit,
            multimodal_lora_nan_guard_triggered=(
                training_result.metrics.multimodal_lora_nan_guard_triggered
            ),
        )
        raise_for_adapter_freeze_audit(adapter_audit)
        adapter_audit_fields = audit_manifest_fields(adapter_audit)
        adapter_artifact_bytes = adapter_audit.adapter_checkpoint_bytes
        adapter_set_hash = _content_hash(training_result.weights_path, training_result.adapter_config_path)
        checkpoint_count = training_result.metrics.checkpoint_count
        resume_ready = training_result.metrics.resume_ready
        latest_checkpoint_path = training_result.metrics.latest_checkpoint_path
        resume_source_path = str(
            training_result.metrics.resume_source_path
            or resume_context["resume_source_path"]
            or ""
        )
        tokens_per_second = training_result.metrics.tokens_per_second
        peak_memory_gb = training_result.metrics.peak_memory_gb
        experiment_group_id = (
            request_ext.get("experiment_group_id", "").strip()
            or _default_experiment_group_id(source_model.model_id, config.adapter_name)
        )
        experiment_group_title = (
            request_ext.get("experiment_group_title", "").strip()
            or (experiment_group_id if request_ext.get("experiment_group_id", "").strip() else config.adapter_name)
        )
        persisted_at_unix_ms = int(time.time() * 1000)

        emit("write_manifest", 0.97)
        manifest = {
            "schema_version": "melix.lora_adapter_package.v1",
            "job_id": job_id,
            "operation": "train_lora",
            "artifact_kind": "adapter",
            "adapter_name": config.adapter_name,
            "preset_id": config.preset_id,
            "preset_title": config.preset_title,
            "source_model": source_model.model_id,
            "source_model_kind": source_model.model_kind,
            "source_model_revision": source_model.revision,
            "source_model_path": source_model.model_path,
            "adapter_scope": adapter_scope["adapter_scope"],
            "training_surface": adapter_scope["training_surface"],
            "component_model_type": adapter_scope["component_model_type"],
            "component_family": adapter_scope["component_family"],
            "component_model_path": adapter_scope["component_model_path"],
            "experiment_group_id": experiment_group_id,
            "experiment_group_title": experiment_group_title,
            "dataset_uri": dataset.dataset_uri,
            "dataset_source_kind": dataset.source_kind,
            "dataset_id": dataset.package.dataset_id,
            "dataset_format": dataset.package.format,
            "dataset_version": dataset.package.version,
            "dataset_sample_count": dataset.package.sample_count,
            "dataset_source_manifest_path": str(dataset.package.manifest_path),
            "dataset_materialized_package_path": str(dataset.materialized_package_path),
            "dataset_cache_key": dataset.cache_key,
            "dataset_cache_hit": dataset.cache_hit,
            "training_mode": config.training_mode,
            "training_objective": config.training_objective,
            "adapter_algorithm": config.adapter_algorithm,
            "adapter_family": config.adapter_family,
            "adapter_capabilities": dict(config.adapter_capabilities),
            "backend_supported": config.backend_supported,
            "unsupported_reason": config.unsupported_reason,
            "preference_loss": config.preference_loss,
            "dataset_contract": config.dataset_contract,
            "dora_enabled": config.adapter_algorithm == "dora",
            "quantization_mode": config.quantization_mode,
            "base_quantization_method": config.base_quantization_method,
            "training_backend": training_result.execution_backend,
            "adapter_set_hash": adapter_set_hash,
            "weights_path": str(training_result.weights_path),
            "adapter_config_path": str(training_result.adapter_config_path),
            "normalized_dataset_manifest_path": str(normalized_snapshot.manifest_path),
            "target_modules": config.expanded_target_modules,
            "rank": config.rank,
            "alpha": config.alpha,
            "dropout": config.dropout,
            "max_steps": config.max_steps,
            "response_only": config.response_only,
            "gradient_checkpointing": config.gradient_checkpointing,
            "gradient_accumulation": config.gradient_accumulation,
            "batch_size": config.batch_size,
            "iters": config.iters,
            "effective_batch_size": config.batch_size * config.gradient_accumulation,
            "optimizer_steps": config.iters // config.gradient_accumulation,
            "mask_prompt": config.mask_prompt,
            "max_seq_length": config.max_seq_length,
            "training.max_steps": config.max_steps,
            "training_duration_ms": training_result.metrics.job_duration_ms,
            "training.job_duration_ms": training_result.metrics.job_duration_ms,
            "training.tokens_seen": training_result.metrics.tokens_seen,
            "training.examples_seen": training_result.metrics.examples_seen,
            "training.loss_final": training_result.metrics.loss_final,
            "training.loss_best": training_result.metrics.loss_best,
            "training.learning_rate_final": training_result.metrics.learning_rate_final,
            "training.tokens_per_second": tokens_per_second,
            "training.peak_memory_gb": peak_memory_gb,
            "training.gradient_checkpointing_enabled": config.gradient_checkpointing,
            "training.response_only_enabled": config.response_only,
            "experiment.checkpoint_count": checkpoint_count,
            "experiment.latest_checkpoint_path": latest_checkpoint_path,
            "experiment.resume_source_path": resume_source_path,
            "experiment.resume_ready": resume_ready,
            "validation_strategy": config.validation_strategy,
            "validation_sample_count": config.validation_sample_count,
            "tokens_seen": training_result.metrics.tokens_seen,
            "examples_seen": training_result.metrics.examples_seen,
            "loss_final": training_result.metrics.loss_final,
            "loss_best": training_result.metrics.loss_best,
            "learning_rate_final": training_result.metrics.learning_rate_final,
            "checkpoint_count": checkpoint_count,
            "latest_checkpoint_path": latest_checkpoint_path,
            "resume_source_path": resume_source_path,
            "resume_ready": resume_ready,
            "tokens_per_second": tokens_per_second,
            "peak_memory_gb": peak_memory_gb,
            "adapter_artifact_bytes": adapter_artifact_bytes,
            "target_repo": config.target_repo,
            "created_at_unix_ms": persisted_at_unix_ms,
            "updated_at_unix_ms": persisted_at_unix_ms,
        }
        manifest.update(adapter_audit_fields)
        if resume_context["resume_manifest_path"] is not None:
            manifest["resume_source_manifest_path"] = str(resume_context["resume_manifest_path"])
        if resume_context["resume_source_job_id"]:
            manifest["resume_source_job_id"] = resume_context["resume_source_job_id"]
        if config.desired_derived_model_alias:
            manifest["desired_derived_model_alias"] = config.desired_derived_model_alias
        # Phase 2 observability: template-aware response-only boundary stats. Only
        # emitted when response_only was requested AND the worker produced a
        # non-zero sample count (chat_messages + valid templates). Delegates
        # field shape to `ResponseOnlyBoundaryAggregate.to_manifest_fields` so
        # rounding / naming stays in one place.
        if (
            config.response_only
            and training_result.metrics.response_only_boundary_sample_count > 0
        ):
            manifest.update(
                ResponseOnlyBoundaryAggregate(
                    sample_count=training_result.metrics.response_only_boundary_sample_count,
                    boundary_min=training_result.metrics.response_only_boundary_min,
                    boundary_max=training_result.metrics.response_only_boundary_max,
                    boundary_mean=training_result.metrics.response_only_boundary_mean,
                ).to_manifest_fields()
            )
        if dataset.hf_reference is not None:
            manifest.update(
                {
                    "hf_dataset_path": dataset.hf_reference.dataset_path,
                    "hf_dataset_name": dataset.hf_reference.dataset_name,
                    "hf_dataset_revision": dataset.hf_reference.dataset_revision,
                    "hf_train_split": dataset.hf_reference.train_split,
                    "hf_valid_split": dataset.hf_reference.valid_split,
                    "chat_feature": dataset.hf_reference.chat_feature,
                    "prompt_feature": dataset.hf_reference.prompt_feature,
                    "completion_feature": dataset.hf_reference.completion_feature,
                    "text_feature": dataset.hf_reference.text_feature,
                    "chosen_feature": dataset.hf_reference.chosen_feature,
                    "rejected_feature": dataset.hf_reference.rejected_feature,
                }
            )
        manifest_path = output_dir / "train_lora.adapter.json"
        manifest["artifact_path"] = str(manifest_path)
        if config.alignment is not None:
            alignment_manifest_path = output_dir / "train_lora.alignment.json"
            candidate_trace_path = ""
            if config.alignment.dataset_contract in {"prompt_candidate", "reward_scored"}:
                candidate_trace_path = str(output_dir / "train_lora.candidates.jsonl")
                _write_alignment_trace(
                    Path(candidate_trace_path),
                    dataset.package.normalized_samples,
                )
            manifest["alignment_run_manifest_path"] = str(alignment_manifest_path)
            manifest["alignment_algorithm"] = config.alignment.alignment_algorithm
            alignment_manifest = _alignment_manifest_payload(
                job_id=job_id,
                source_model=source_model,
                config=config,
                dataset=dataset,
                training_result=training_result,
                adapter_manifest_path=manifest_path,
                candidate_trace_path=candidate_trace_path,
                created_at_unix_ms=persisted_at_unix_ms,
            )
            alignment_manifest_path.write_text(
                json.dumps(alignment_manifest, indent=2) + "\n",
                encoding="utf-8",
            )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self._experiment_store.persist_training_run(
            jobs_root=jobs_root,
            manifest=manifest,
            manifest_path=manifest_path,
        )
        return LoRATrainingPipelineResult(manifest=manifest, manifest_path=manifest_path)


def _resolve_adapter_scope_metadata(source_model: common_pb2.ModelSpec) -> dict[str, str]:
    ext = source_model.ext
    adapter_scope = ext.get("melix.lora.adapter_scope", "").strip()
    if not adapter_scope and source_model.model_kind == "text":
        adapter_scope = "model"
    if source_model.model_kind != "text" and not adapter_scope:
        raise AssertionError(
            "_resolve_adapter_scope_metadata called on non-text model with no adapter_scope; "
            "caller should have rejected this model via _validate_lora_training_surface."
        )
    training_surface = ext.get("melix.lora.training_surface", "").strip() or adapter_scope
    component_model_type = (
        ext.get("melix.lora.component_model_type", "").strip()
        or ext.get(f"melix.component.{adapter_scope}.model_type", "").strip()
    )
    component_family = (
        ext.get("melix.lora.family_id", "").strip()
        or ext.get(f"melix.component.{adapter_scope}.family_id", "").strip()
        or ext.get("text_family_id", "").strip()
    )
    component_model_path = (
        ext.get("melix.lora.base_model_path", "").strip()
        or ext.get(f"melix.component.{adapter_scope}.path", "").strip()
        or source_model.model_path
    )
    return {
        "adapter_scope": adapter_scope,
        "training_surface": training_surface,
        "component_model_type": component_model_type,
        "component_family": component_family,
        "component_model_path": component_model_path,
    }


def _int_ext(ext: dict[str, str], key: str) -> int:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return 0
    return int(raw_value)


def _write_alignment_trace(path: Path, samples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample) + "\n")


def _validate_alignment_inputs(*, config: LoRATrainingConfig, samples: list[dict[str, Any]]) -> None:
    alignment = config.alignment
    if alignment is None:
        return
    if alignment.alignment_algorithm == "grpo":
        for sample_index, sample in enumerate(samples):
            candidates = sample.get("candidates")
            candidate_count = len(candidates) if isinstance(candidates, list) else 0
            if candidate_count < alignment.grpo_candidate_count:
                raise ModelOperationError(
                    code="invalid_alignment_dataset",
                    message="GRPO samples must include at least grpo_candidate_count candidates.",
                    details={
                        "sample_index": str(sample_index),
                        "candidate_count": str(candidate_count),
                        "grpo_candidate_count": str(alignment.grpo_candidate_count),
                    },
                )
    if alignment.alignment_algorithm == "rlhf":
        _validate_reward_model_manifest(alignment.reward_model_manifest_path)


def _validate_reward_model_manifest(manifest_path: str) -> None:
    path = Path(manifest_path).expanduser()
    if not path.is_file():
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="reward_model_manifest_path must point to a readable reward model manifest.",
            details={"reward_model_manifest_path": manifest_path},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="reward_model_manifest_path must point to a readable JSON manifest.",
            details={"reward_model_manifest_path": manifest_path},
        ) from exc
    if not isinstance(payload, dict) or not str(payload.get("schema_version", "")).strip():
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="reward model manifest must include schema_version.",
            details={"reward_model_manifest_path": manifest_path},
        )


def _alignment_manifest_payload(
    *,
    job_id: str,
    source_model: common_pb2.ModelSpec,
    config: LoRATrainingConfig,
    dataset: ResolvedTrainingDatasetPackage,
    training_result: TrainingResult,
    adapter_manifest_path: Path,
    candidate_trace_path: str,
    created_at_unix_ms: int,
) -> dict[str, Any]:
    alignment = config.alignment
    assert alignment is not None
    assert config.dataset_contract == alignment.dataset_contract
    metrics = {
        "training_duration_ms": training_result.metrics.job_duration_ms,
        "loss_final": training_result.metrics.loss_final,
        "loss_best": training_result.metrics.loss_best,
        "tokens_seen": training_result.metrics.tokens_seen,
        "examples_seen": training_result.metrics.examples_seen,
    }
    if alignment.dataset_contract == "preference_pair":
        metrics.update(
            {
                "preference_loss_config": config.preference_loss,
                "preference_loss_final": training_result.metrics.preference_loss_final,
                "chosen_logprob_mean": training_result.metrics.chosen_logprob_mean,
                "rejected_logprob_mean": training_result.metrics.rejected_logprob_mean,
                "chosen_rejected_margin": training_result.metrics.chosen_rejected_margin,
                "win_rate_proxy": training_result.metrics.win_rate_proxy,
            }
        )
    reward_summary = _reward_summary(dataset.package.normalized_samples)
    if reward_summary:
        metrics.update(reward_summary)
    if alignment.dataset_contract in {"prompt_candidate", "reward_scored"}:
        metrics.update(
            {
                "policy_update_count": training_result.metrics.policy_update_count,
                "selected_candidate_count": training_result.metrics.selected_candidate_count,
                "policy_update_trace_path": training_result.metrics.policy_update_trace_path,
                "kl_penalty": alignment.kl_penalty,
                "candidate_generation_mode": alignment.candidate_generation_mode,
                "candidate_scoring_mode": alignment.candidate_scoring_mode,
            }
        )
        if training_result.metrics.candidate_generation_backend:
            metrics["candidate_generation_backend"] = training_result.metrics.candidate_generation_backend
        if training_result.metrics.reward_scoring_backend:
            metrics["reward_scoring_backend"] = training_result.metrics.reward_scoring_backend
        if training_result.metrics.generated_candidate_count:
            metrics["generated_candidate_count"] = training_result.metrics.generated_candidate_count
        if training_result.metrics.policy_update_count or training_result.metrics.policy_update_trace_path:
            metrics["reward_mean"] = training_result.metrics.reward_mean
            metrics["reward_p50"] = training_result.metrics.reward_p50
            metrics["reward_p95"] = training_result.metrics.reward_p95
        if training_result.metrics.candidate_group_count:
            metrics["candidate_group_count"] = training_result.metrics.candidate_group_count
            metrics["candidate_group_reward_margin_mean"] = (
                training_result.metrics.candidate_group_reward_margin_mean
            )
            metrics["candidate_group_reward_variance_mean"] = (
                training_result.metrics.candidate_group_reward_variance_mean
            )

    return {
        "schema_version": "melix.alignment_run.v1",
        "operation": "train_alignment",
        "job_id": job_id,
        "source_model": source_model.model_id,
        "source_model_revision": source_model.revision,
        "source_model_path": source_model.model_path,
        "training_backend": training_result.execution_backend,
        "training_mode": config.training_mode,
        "training_objective": config.training_objective,
        "alignment_algorithm": alignment.alignment_algorithm,
        "dataset_contract": alignment.dataset_contract,
        "dataset_uri": dataset.dataset_uri,
        "dataset_format": dataset.package.format,
        "candidate_generation_mode": alignment.candidate_generation_mode,
        "candidate_scoring_mode": alignment.candidate_scoring_mode,
        "adapter_manifest_path": str(adapter_manifest_path),
        "reference_model_path": alignment.reference_model_path,
        "reward_model_manifest_path": alignment.reward_model_manifest_path,
        "candidate_trace_path": candidate_trace_path,
        "grpo_candidate_count": alignment.grpo_candidate_count,
        "kl_penalty": alignment.kl_penalty,
        "adapter_set_hash": _content_hash(
            training_result.weights_path,
            training_result.adapter_config_path,
        ),
        "checkpoint_count": training_result.metrics.checkpoint_count,
        "latest_checkpoint_path": training_result.metrics.latest_checkpoint_path,
        "metrics": metrics,
        "created_at_unix_ms": created_at_unix_ms,
        "updated_at_unix_ms": created_at_unix_ms,
    }


def _reward_summary(samples: list[dict[str, Any]]) -> dict[str, float | int]:
    scores: list[float] = []
    score_total = 0.0
    candidate_group_margins: list[float] = []
    candidate_group_margin_total = 0.0
    candidate_group_variance_total = 0.0
    for sample in samples:
        if "reward_score" in sample:
            reward_score = float(sample["reward_score"])
            scores.append(reward_score)
            score_total += reward_score
        candidates = sample.get("candidates")
        candidate_scores: list[float] = []
        candidate_score_min: float | None = None
        candidate_score_max: float | None = None
        candidate_score_total = 0.0
        candidate_score_square_total = 0.0
        if isinstance(candidates, list):
            for candidate in candidates:
                if isinstance(candidate, dict) and "score" in candidate:
                    candidate_score = float(candidate["score"])
                    candidate_scores.append(candidate_score)
                    candidate_score_total += candidate_score
                    candidate_score_square_total += candidate_score * candidate_score
                    if candidate_score_min is None or candidate_score < candidate_score_min:
                        candidate_score_min = candidate_score
                    if candidate_score_max is None or candidate_score > candidate_score_max:
                        candidate_score_max = candidate_score
        if candidate_scores:
            scores.extend(candidate_scores)
            score_total += candidate_score_total
        candidate_score_count = len(candidate_scores)
        if candidate_score_count >= 2:
            assert candidate_score_min is not None
            assert candidate_score_max is not None
            group_mean = candidate_score_total / candidate_score_count
            candidate_group_margin = candidate_score_max - candidate_score_min
            candidate_group_variance = (
                candidate_score_square_total / candidate_score_count
            ) - (group_mean * group_mean)
            candidate_group_margins.append(candidate_group_margin)
            candidate_group_margin_total += candidate_group_margin
            candidate_group_variance_total += candidate_group_variance
    if not scores:
        return {}
    ordered = sorted(scores)
    summary: dict[str, float | int] = {
        "reward_mean": score_total / len(scores),
        "reward_p50": _percentile_value(ordered, 0.5),
        "reward_p95": _percentile_value(ordered, 0.95),
    }
    if candidate_group_margins:
        ordered_margins = sorted(candidate_group_margins)
        candidate_group_count = len(candidate_group_margins)
        summary.update(
            {
                "candidate_group_count": candidate_group_count,
                "candidate_group_reward_margin_mean": candidate_group_margin_total
                / candidate_group_count,
                "candidate_group_reward_margin_p50": _percentile_value(
                    ordered_margins,
                    0.5,
                ),
                "candidate_group_reward_margin_p95": _percentile_value(
                    ordered_margins,
                    0.95,
                ),
                "candidate_group_reward_variance_mean": candidate_group_variance_total
                / candidate_group_count,
            }
        )
    return summary


def _percentile_value(ordered_values: list[float], percentile: float) -> float:
    if len(ordered_values) == 1:
        return ordered_values[0]
    position = min(
        len(ordered_values) - 1,
        max(0.0, (len(ordered_values) - 1) * percentile),
    )
    lower_index = int(position)
    upper_index = min(len(ordered_values) - 1, lower_index + 1)
    if lower_index == upper_index:
        return ordered_values[lower_index]
    weight = position - lower_index
    return ordered_values[lower_index] + (
        ordered_values[upper_index] - ordered_values[lower_index]
    ) * weight


_CONTENT_HASH_CHUNK_SIZE = 1024 * 1024



def _content_hash(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with path.open("rb") as handle:
            while chunk := handle.read(_CONTENT_HASH_CHUNK_SIZE):
                digest.update(chunk)
    return digest.hexdigest()[:16]


def _resolve_resume_context(ext: dict[str, str]) -> dict[str, Any]:
    raw_resume_path = next(
        (
            ext.get(key, "").strip()
            for key in (
                "resume_source_path",
                "resume_from_path",
                "resume_adapter_file",
                "resume_manifest_path",
                "source_adapter_path",
            )
            if ext.get(key, "").strip()
        ),
        "",
    )
    if not raw_resume_path:
        return {
            "resume_source_path": None,
            "resume_manifest_path": None,
            "resume_source_job_id": "",
        }

    candidate_path = Path(raw_resume_path).expanduser()
    if not candidate_path.exists():
        raise ModelOperationError(
            code="invalid_resume_source",
            message=f"Resume source does not exist: {candidate_path}",
        )

    if candidate_path.is_file() and candidate_path.suffix == ".json":
        manifest = _load_manifest_payload(candidate_path)
        resolved_resume_path = _resolve_resume_path_from_manifest(candidate_path, manifest)
        return {
            "resume_source_path": resolved_resume_path,
            "resume_manifest_path": candidate_path.resolve(),
            "resume_source_job_id": str(manifest.get("job_id", "")).strip(),
        }

    if candidate_path.is_dir():
        candidate_path = _latest_checkpoint_from_directory(candidate_path)

    return {
        "resume_source_path": candidate_path.resolve(),
        "resume_manifest_path": None,
        "resume_source_job_id": "",
    }


def _load_manifest_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelOperationError(
            code="invalid_resume_source",
            message=f"Resume manifest is unreadable: {path}",
        ) from exc
    if isinstance(payload, dict) is False:
        raise ModelOperationError(
            code="invalid_resume_source",
            message=f"Resume manifest must be a JSON object: {path}",
        )
    return payload


def _resolve_resume_path_from_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    for key in ("latest_checkpoint_path", "weights_path"):
        raw_value = str(manifest.get(key, "")).strip()
        if raw_value:
            return _validated_resume_path(Path(raw_value).expanduser(), source_label=str(path))
    raise ModelOperationError(
        code="invalid_resume_source",
        message=f"Resume manifest does not expose a checkpoint or weights path: {path}",
    )


def _latest_checkpoint_from_directory(path: Path) -> Path:
    pending: list[str] = [os.fspath(path)]
    latest_checkpoint_path = ""
    latest_checkpoint_key: tuple[int, str] | None = None
    while pending:
        current_dir = pending.pop()
        with os.scandir(current_dir) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                    continue
                if not entry.name.endswith(".safetensors") or entry.is_dir(follow_symlinks=True):
                    continue
                numbers = _NUMERIC_TOKEN_RE.findall(entry.path)
                checkpoint_key = (int(numbers[-1]) if numbers else -1, entry.path)
                if latest_checkpoint_key is None or checkpoint_key > latest_checkpoint_key:
                    latest_checkpoint_path = entry.path
                    latest_checkpoint_key = checkpoint_key

    if latest_checkpoint_key is None:
        raise ModelOperationError(
            code="invalid_resume_source",
            message=f"Resume directory does not contain adapter weights: {path}",
        )

    return Path(latest_checkpoint_path).resolve()


def _validated_resume_path(path: Path, *, source_label: str) -> Path:
    if path.exists() is False:
        raise ModelOperationError(
            code="invalid_resume_source",
            message=f"Resume source from {source_label} does not exist: {path}",
        )
    if path.is_dir():
        return _latest_checkpoint_from_directory(path)
    return path.resolve()


def _default_experiment_group_id(source_model_id: str, adapter_name: str) -> str:
    normalized_source_model_id = source_model_id.strip() or "model"
    normalized_adapter_name = adapter_name.strip() or "adapter"
    return f"{normalized_source_model_id}:{normalized_adapter_name}"
