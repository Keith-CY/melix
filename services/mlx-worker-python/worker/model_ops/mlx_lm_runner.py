from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass, replace
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterable

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.multimodal_lora_contracts import (
    audit_manifest_fields,
    audit_trainable_module_tree,
)
from worker.model_ops.response_only_boundary import (
    ResponseOnlyBoundary,
    ResponseOnlyBoundaryAggregate,
    aggregate_response_only_boundaries,
    compute_response_only_boundary,
)
from worker.model_ops.training_config import AlignmentTrainingConfig, LoRATrainingConfig
from worker.model_ops.training_dataset_chunker import (
    ChunkStats,
    chunk_long_samples,
)

_RESULT_PREFIX = "__MELIX_MLX_RESULT__="
_NUMERIC_TOKEN_RE = re.compile(r"\d+")
# Sentinel tied to mlx-lm's internal error wording. Keep the mlx-lm pin in
# pyproject.toml tight: any upstream wording change would silently disable the
# no-strict retry for QLoRA loads. Update both the sentinel and tests together
# when bumping the mlx-lm version.
_MLX_LM_UNMATCHED_WEIGHT_MARKERS = ("parameters not in model",)
_LOGGER = logging.getLogger("melix.lora.mlx_lm_runner")


@dataclass(frozen=True)
class TrainingMetrics:
    job_duration_ms: float
    tokens_seen: int
    examples_seen: int
    loss_final: float
    loss_best: float
    learning_rate_final: float
    checkpoint_count: int = 0
    resume_ready: bool = False
    latest_checkpoint_path: str = ""
    resume_source_path: str = ""
    tokens_per_second: float = 0.0
    peak_memory_gb: float = 0.0
    profile_artifact_path: str = ""
    # Milestone #43 Phase 2: template-aware response-only boundary observability.
    # Populated for chat_messages datasets when response_only is requested. Zero
    # when the sample format doesn't support response-only masking.
    response_only_boundary_sample_count: int = 0
    response_only_boundary_min: int = 0
    response_only_boundary_max: int = 0
    response_only_boundary_mean: float = 0.0
    response_only_response_tokens_min: int = 0
    response_only_response_tokens_max: int = 0
    response_only_response_tokens_mean: float = 0.0
    response_only_trainable_response_tokens_min: int = 0
    response_only_trainable_response_tokens_max: int = 0
    response_only_trainable_response_tokens_mean: float = 0.0
    response_only_trainable_response_token_count: int = 0
    response_only_truncated_response_sample_count: int = 0
    response_only_fully_truncated_response_sample_count: int = 0
    # Milestone #43 Phase 3B: long-context chunking observability. ``chunked_enabled``
    # is True iff chunk_long_samples ran; ``chunk_count`` is the post-chunking
    # sample count (equal to ``source_sample_count`` when no sample exceeded
    # chunk_size). Zero/False on the baseline path so every pre-Phase-3B
    # receipt stays forward-compatible.
    chunked_enabled: bool = False
    chunk_count: int = 0
    source_sample_count: int = 0
    preference_loss_final: float | None = None
    chosen_logprob_mean: float | None = None
    rejected_logprob_mean: float | None = None
    chosen_rejected_margin: float | None = None
    win_rate_proxy: float | None = None
    reward_mean: float = 0.0
    reward_p50: float = 0.0
    reward_p95: float = 0.0
    reward_component_final_answer_mean: float = 0.0
    reward_component_tool_efficiency_mean: float = 0.0
    reward_component_format_mean: float = 0.0
    reward_component_fatal_failure_mean: float = 0.0
    reward_component_total_mean: float = 0.0
    fatal_trace_count: int = 0
    fatal_aware_grpo_schema_version: str = ""
    fatal_candidate_count: int = 0
    selected_fatal_candidate_count: int = 0
    advantage_clamped_candidate_count: int = 0
    policy_update_count: int = 0
    selected_candidate_count: int = 0
    candidate_group_count: int = 0
    candidate_group_reward_margin_mean: float = 0.0
    candidate_group_reward_variance_mean: float = 0.0
    policy_update_trace_path: str = ""
    candidate_reward_trace_path: str = ""
    candidate_reward_trace_count: int = 0
    candidate_reward_trace_schema_version: str = ""
    candidate_generation_mode: str = ""
    candidate_generation_backend: str = ""
    candidate_scoring_mode: str = ""
    reward_scoring_backend: str = ""
    generated_candidate_count: int = 0
    rollout_manifest_schema_version: str = ""
    rollout_candidate_count: int = 0
    rollout_reward_policy_id: str = ""
    rollout_reference_model_path: str = ""
    rollout_trajectory_digest: str = ""
    multimodal_lora_nan_guard_triggered: bool = False
    unexpected_frozen_param_count: int = 0
    adapter_checkpoint_bytes: int = 0
    adapter_freeze_audit: dict[str, Any] | None = None
    completion_loss: float | None = None
    round_trip_passed: bool = False
    grad_norm: float = 0.0


@dataclass(frozen=True)
class TrainingRequest:
    job_id: str
    base_model_id: str
    model_path: Path
    model_revision: str
    adapter_output_dir: Path
    normalized_dataset_dir: Path
    config: LoRATrainingConfig
    dataset_format: str
    resume_source_path: Path | None = None
    source_model_kind: str = "text"
    source_model_ext: dict[str, str] | None = None


@dataclass(frozen=True)
class TrainingResult:
    weights_path: Path
    adapter_config_path: Path
    metrics: TrainingMetrics
    execution_backend: str


@dataclass(frozen=True)
class ActivationMetrics:
    job_duration_ms: float


@dataclass(frozen=True)
class ActivationRequest:
    job_id: str
    base_model_id: str
    model_path: Path
    adapter_dir: Path
    adapter_manifest_path: Path
    derived_model_dir: Path
    activation_mode: str


@dataclass(frozen=True)
class ActivationResult:
    derived_model_dir: Path
    manifest_path: Path
    metrics: ActivationMetrics
    execution_backend: str


class NativeExecutionUnavailable(RuntimeError):
    pass


def _requires_alignment_trainer(config: LoRATrainingConfig) -> bool:
    return (
        config.training_objective in {"preference", "alignment_rl"}
        or config.alignment is not None
    )


def _alignment_trainer_unavailable_error(config: LoRATrainingConfig) -> ModelOperationError:
    alignment_algorithm = (
        config.alignment.alignment_algorithm
        if config.alignment is not None
        else config.training_mode
    )
    return ModelOperationError(
        code="unsupported_alignment_trainer",
        message=(
            f"training_mode={config.training_mode} requires a real alignment "
            "trainer backend; the default MLX-LM runner only supports "
            "supervised LoRA/QLoRA/DoRA execution."
        ),
        details={
            "training_mode": config.training_mode,
            "training_objective": config.training_objective,
            "alignment_algorithm": alignment_algorithm,
            "required_backend": "alignment_trainer",
            "available_backend": "mlx_lm_lora_supervised",
        },
    )


class MLXLMRunner:
    def __init__(self, policy_runtime: Any | None = None, reward_runtime: Any | None = None) -> None:
        self._policy_runtime = policy_runtime
        self._reward_runtime = reward_runtime

    def train(self, request: TrainingRequest) -> TrainingResult:
        if (
            _requires_alignment_trainer(request.config)
            and not self.supports_alignment_training(request.config)
        ):
            raise _alignment_trainer_unavailable_error(request.config)
        try:
            result = self.train_native(request)
            return result if result.execution_backend else replace(result, execution_backend="native")
        except NativeExecutionUnavailable as exc:
            result = self.train_subprocess(request, exc)
            return replace(result, execution_backend="subprocess")

    def supports_alignment_training(self, config: LoRATrainingConfig) -> bool:
        return config.training_objective in {"preference", "alignment_rl"}

    def activate(self, request: ActivationRequest) -> ActivationResult:
        try:
            result = self.activate_native(request)
            return replace(result, execution_backend="native")
        except NativeExecutionUnavailable as exc:
            result = self.activate_subprocess(request, exc)
            return replace(result, execution_backend="subprocess")

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        if request.config.training_objective == "preference":
            from worker.model_ops.preference_training import train_preference_native

            return train_preference_native(request)
        if request.config.training_objective == "alignment_rl":
            from worker.model_ops.rl_alignment_training import train_alignment_rl_trace

            return train_alignment_rl_trace(
                request,
                policy_runtime=self._policy_runtime,
                reward_runtime=self._reward_runtime,
            )

        try:
            from mlx_lm.lora import train_model
            from mlx_lm.tuner.callbacks import TrainingCallback
            from mlx_lm.tuner.datasets import load_local_dataset
            from mlx_lm.utils import load
        except ModuleNotFoundError as exc:
            raise NativeExecutionUnavailable("MLX-LM is not available in the current runtime.") from exc

        class MetricsCollector(TrainingCallback):
            def __init__(self) -> None:
                self.losses: list[float] = []
                self.learning_rates: list[float] = []
                self.tokens_seen = 0

            def on_train_loss_report(self, train_info: dict) -> None:
                if "train_loss" in train_info:
                    self.losses.append(float(train_info["train_loss"]))
                if "learning_rate" in train_info:
                    self.learning_rates.append(float(train_info["learning_rate"]))
                if "trained_tokens" in train_info:
                    self.tokens_seen = int(train_info["trained_tokens"])

            def on_val_loss_report(self, val_info: dict) -> None:
                if "val_loss" in val_info:
                    self.losses.append(float(val_info["val_loss"]))

        collector = MetricsCollector()
        started_at = time.perf_counter()
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        _reset_mlx_peak_memory_probe()

        model, tokenizer = _load_lora_training_model(request, load)
        args = _mlx_lora_namespace(request)
        # Phase 3B: when chunked_training is enabled, rewrite train.jsonl with
        # chunked samples before MLX-LM reads it. No-op otherwise; the
        # stats returned carry enabled=False + chunk_count=0 so they fall
        # through into forward-compatible defaults on TrainingMetrics.
        chunk_stats = _maybe_chunk_training_dataset(request, tokenizer)
        _validate_media_token_truncation(request)
        train_set, valid_set, _ = load_local_dataset(
            request.normalized_dataset_dir,
            tokenizer,
            args,
        )
        # Phase 2 observability: probe the chat-template boundary that MLX-LM
        # uses internally so the manifest records which token range would be
        # masked under response_only. Reuses the `train_set` produced by
        # `load_local_dataset` and calls its `process()` method — the exact
        # path MLX-LM uses at training time — so the aggregate is bit-exact
        # with what MLX-LM's default_loss will see.
        boundary_aggregate = _probe_response_only_boundary(request, train_set)
        _validate_response_only_trainable_tokens(request, boundary_aggregate)

        try:
            train_model(args, model, train_set, valid_set, training_callback=collector)
        except Exception as exc:
            raise ModelOperationError(
                code="backend_training_failure",
                message=f"MLX-LM training failed: {exc}",
            ) from exc

        duration_ms = (time.perf_counter() - started_at) * 1000.0
        losses = collector.losses or [0.0]
        learning_rates = collector.learning_rates or [request.config.learning_rate]
        tokens_per_second = 0.0
        if duration_ms > 0.0 and collector.tokens_seen > 0:
            tokens_per_second = collector.tokens_seen / (duration_ms / 1000.0)
        checkpoint_count, latest_checkpoint_path = _checkpoint_summary(request.adapter_output_dir)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        live_audit = audit_trainable_module_tree(
            model,
            allowed_target_modules=request.config.expanded_target_modules,
            source_model_kind=request.source_model_kind,
            source_model_ext=request.source_model_ext or {},
        )
        live_audit_fields = audit_manifest_fields(live_audit)
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=request.adapter_output_dir / "adapter_config.json",
            metrics=TrainingMetrics(
                job_duration_ms=duration_ms,
                tokens_seen=collector.tokens_seen,
                examples_seen=request.config.batch_size * request.config.iters,
                loss_final=losses[-1],
                loss_best=min(losses),
                learning_rate_final=learning_rates[-1],
                checkpoint_count=checkpoint_count,
                resume_ready=latest_checkpoint_path != "",
                latest_checkpoint_path=latest_checkpoint_path,
                resume_source_path=str(request.resume_source_path) if request.resume_source_path is not None else "",
                tokens_per_second=tokens_per_second,
                peak_memory_gb=_mlx_peak_memory_gb(),
                response_only_boundary_sample_count=boundary_aggregate.sample_count,
                response_only_boundary_min=boundary_aggregate.boundary_min,
                response_only_boundary_max=boundary_aggregate.boundary_max,
                response_only_boundary_mean=boundary_aggregate.boundary_mean,
                response_only_response_tokens_min=boundary_aggregate.response_tokens_min,
                response_only_response_tokens_max=boundary_aggregate.response_tokens_max,
                response_only_response_tokens_mean=boundary_aggregate.response_tokens_mean,
                response_only_trainable_response_tokens_min=boundary_aggregate.trainable_response_tokens_min,
                response_only_trainable_response_tokens_max=boundary_aggregate.trainable_response_tokens_max,
                response_only_trainable_response_tokens_mean=boundary_aggregate.trainable_response_tokens_mean,
                response_only_trainable_response_token_count=boundary_aggregate.trainable_response_token_count,
                response_only_truncated_response_sample_count=boundary_aggregate.truncated_response_sample_count,
                response_only_fully_truncated_response_sample_count=boundary_aggregate.fully_truncated_response_sample_count,
                chunked_enabled=chunk_stats.enabled,
                chunk_count=chunk_stats.chunk_count,
                source_sample_count=chunk_stats.source_sample_count,
                unexpected_frozen_param_count=int(live_audit_fields["unexpected_frozen_param_count"]),
                adapter_checkpoint_bytes=weights_path.stat().st_size if weights_path.is_file() else 0,
                adapter_freeze_audit=live_audit_fields["adapter_freeze_audit"],
            ),
            execution_backend="native",
        )

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        payload_path = request.adapter_output_dir / ".melix_train_request.json"
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(_serialize_training_request(request), indent=2) + "\n", encoding="utf-8")
        result = self._run_subprocess("train", payload_path, error_code="backend_training_failure")
        return _deserialize_training_result(result)

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        try:
            from mlx.utils import tree_unflatten
            from mlx_lm.utils import load, save
        except ModuleNotFoundError as exc:
            raise NativeExecutionUnavailable("MLX-LM is not available in the current runtime.") from exc

        started_at = time.perf_counter()
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        try:
            model, tokenizer, config = load(
                str(request.model_path),
                adapter_path=str(request.adapter_dir),
                return_config=True,
            )
            fused_linears = [
                (name, module.fuse(dequantize=False))
                for name, module in model.named_modules()
                if hasattr(module, "fuse")
            ]
            if fused_linears:
                model.update_modules(tree_unflatten(fused_linears))
            save(
                request.derived_model_dir,
                str(request.model_path),
                model,
                tokenizer,
                config,
                donate_model=False,
            )
        except Exception as exc:
            raise ModelOperationError(
                code="activation_failure",
                message=f"MLX-LM activation failed: {exc}",
            ) from exc

        manifest_path = request.derived_model_dir / "manifest.json"
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=manifest_path,
            metrics=ActivationMetrics(job_duration_ms=duration_ms),
            execution_backend="native",
        )

    def activate_subprocess(self, request: ActivationRequest, reason: Exception) -> ActivationResult:
        payload_path = request.derived_model_dir.parent / ".melix_activation_request.json"
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(_serialize_activation_request(request), indent=2) + "\n", encoding="utf-8")
        result = self._run_subprocess("activate", payload_path, error_code="activation_failure")
        return _deserialize_activation_result(result)

    def _run_subprocess(self, command: str, payload_path: Path, *, error_code: str) -> dict:
        project_root = Path(__file__).resolve().parents[2]
        process = subprocess.run(
            [
                "uv",
                "run",
                "--project",
                str(project_root),
                "--extra",
                "mlx",
                "python",
                "-m",
                "worker.model_ops.mlx_lm_runner",
                command,
                str(payload_path),
            ],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=False,
        )
        if process.returncode != 0:
            raise ModelOperationError(
                code=error_code,
                message=(process.stderr or process.stdout or "MLX subprocess failed.").strip(),
            )

        payload = _extract_structured_result_payload(process.stdout)
        if payload is not None:
            return payload

        raise ModelOperationError(
            code=error_code,
            message="MLX subprocess completed without returning a structured result.",
        )


def _extract_structured_result_payload(stdout: str) -> dict[str, object] | None:
    search_end = len(stdout)
    prefix = _RESULT_PREFIX
    prefix_length = len(prefix)
    while True:
        prefix_index = stdout.rfind(prefix, 0, search_end)
        if prefix_index < 0:
            return None
        if prefix_index > 0:
            previous_character = stdout[prefix_index - 1]
            if previous_character != "\n" and previous_character != "\r":
                search_end = prefix_index
                continue
        newline_index = stdout.find("\n", prefix_index)
        if newline_index >= 0:
            line_end = newline_index
        else:
            line_end = len(stdout)
            carriage_index = stdout.find("\r", prefix_index)
            if carriage_index >= 0:
                line_end = carriage_index
        return json.loads(stdout[prefix_index + prefix_length:line_end])


def _mlx_lora_namespace(request: TrainingRequest):
    import types

    return types.SimpleNamespace(
        seed=0,
        train=True,
        data=str(request.normalized_dataset_dir),
        model=str(request.model_path),
        fine_tune_type=request.config.adapter_algorithm,
        adapter_family=request.config.adapter_family,
        adapter_capabilities=dict(request.config.adapter_capabilities),
        adapter_loader_kwargs=dict(request.config.adapter_loader_kwargs),
        optimizer="adam",
        optimizer_config={"adam": {}, "adamw": {}, "muon": {}, "sgd": {}, "adafactor": {}},
        num_layers=request.config.num_layers,
        batch_size=request.config.batch_size,
        iters=request.config.iters,
        val_batches=0,
        learning_rate=request.config.learning_rate,
        steps_per_report=request.config.steps_per_report,
        steps_per_eval=request.config.steps_per_eval,
        grad_accumulation_steps=request.config.gradient_accumulation,
        resume_adapter_file=(
            str(request.resume_source_path)
            if request.resume_source_path is not None
            else None
        ),
        adapter_path=str(request.adapter_output_dir),
        save_every=request.config.steps_per_save,
        test=False,
        test_batches=0,
        max_seq_length=request.config.max_seq_length,
        config=None,
        grad_checkpoint=request.config.gradient_checkpointing,
        lr_schedule=None,
        lora_parameters={
            "rank": request.config.rank,
            "dropout": request.config.dropout,
            "scale": request.config.alpha,
            "keys": request.config.backend_target_modules,
        },
        mask_prompt=request.config.mask_prompt,
        report_to=None,
        project_name=None,
    )


def _load_lora_training_model(request: TrainingRequest, load_fn: Any) -> tuple[Any, Any]:
    try:
        return load_fn(str(request.model_path), lazy=False)
    except ValueError as exc:
        if not _should_retry_quantized_lora_load_without_strict(request, exc):
            raise
        from mlx_lm.utils import _download, load_model, load_tokenizer

        _LOGGER.warning(
            "Retrying quantized LoRA model load with strict=False after MLX-LM "
            "reported unmatched weight tensors for %s.",
            request.model_path,
        )
        model_path = _download(
            str(request.model_path),
            revision=request.model_revision or None,
        )
        model, config = load_model(model_path, lazy=False, strict=False)
        tokenizer = load_tokenizer(
            model_path,
            None,
            eos_token_ids=config.get("eos_token_id", None),
        )
        return model, tokenizer


def _should_retry_quantized_lora_load_without_strict(
    request: TrainingRequest,
    exc: ValueError,
) -> bool:
    if not _is_mlx_lm_unmatched_weight_error(exc):
        return False
    return (
        request.config.training_mode == "qlora"
        or request.config.quantization_mode == "quantized_base"
    )


def _is_mlx_lm_unmatched_weight_error(exc: ValueError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _MLX_LM_UNMATCHED_WEIGHT_MARKERS)


def _serialize_training_request(request: TrainingRequest) -> dict:
    payload = {
        "job_id": request.job_id,
        "base_model_id": request.base_model_id,
        "model_path": str(request.model_path),
        "model_revision": request.model_revision,
        "adapter_output_dir": str(request.adapter_output_dir),
        "normalized_dataset_dir": str(request.normalized_dataset_dir),
        "resume_source_path": (
            str(request.resume_source_path)
            if request.resume_source_path is not None
            else ""
        ),
        "dataset_format": request.dataset_format,
        "source_model_kind": request.source_model_kind,
        "source_model_ext": dict(request.source_model_ext or {}),
        "config": asdict(request.config),
    }
    return payload


def _deserialize_training_request(payload: dict) -> TrainingRequest:
    config_payload = dict(payload["config"])
    alignment_payload = config_payload.get("alignment")
    if isinstance(alignment_payload, dict):
        config_payload["alignment"] = AlignmentTrainingConfig(**alignment_payload)
    config = LoRATrainingConfig(**config_payload)
    return TrainingRequest(
        job_id=str(payload["job_id"]),
        base_model_id=str(payload["base_model_id"]),
        model_path=Path(payload["model_path"]),
        model_revision=str(payload["model_revision"]),
        adapter_output_dir=Path(payload["adapter_output_dir"]),
        normalized_dataset_dir=Path(payload["normalized_dataset_dir"]),
        config=config,
        dataset_format=str(payload["dataset_format"]),
        resume_source_path=(
            Path(payload["resume_source_path"])
            if str(payload.get("resume_source_path", "")).strip()
            else None
        ),
        source_model_kind=str(payload.get("source_model_kind", "") or "text"),
        source_model_ext={
            str(key): str(value)
            for key, value in dict(payload.get("source_model_ext", {}) or {}).items()
        },
    )


def _serialize_training_result(result: TrainingResult) -> dict:
    return {
        "weights_path": str(result.weights_path),
        "adapter_config_path": str(result.adapter_config_path),
        "metrics": asdict(result.metrics),
        "execution_backend": result.execution_backend,
    }


def _deserialize_training_result(payload: dict) -> TrainingResult:
    return TrainingResult(
        weights_path=Path(payload["weights_path"]),
        adapter_config_path=Path(payload["adapter_config_path"]),
        metrics=TrainingMetrics(**payload["metrics"]),
        execution_backend=str(payload["execution_backend"]),
    )


_PROBE_LOGGER = logging.getLogger("melix.lora.response_only_boundary")


def _probe_response_only_boundary(
    request: TrainingRequest, train_set: Any
) -> ResponseOnlyBoundaryAggregate:
    """Summarize MLX-LM's own (tokens, offset) output across the train set.

    Delegates to the already-built `train_set` (MLX-LM's ``ChatDataset``) so
    that the aggregate is bit-exact with what the trainer's ``default_loss``
    will see and we don't re-read or re-tokenize the normalized dataset.
    Streams via a generator into ``aggregate_response_only_boundaries`` so
    there is no intermediate per-sample list.

    Returns an empty aggregate when the dataset format cannot produce
    response-only supervision, when ``response_only`` is disabled, or when the
    train_set does not expose the ``process``/``__len__``/``__getitem__``
    interface. Never raises — the metric stays additive. Per-sample skips
    (tools-only turns, custom roles, tokenizer errors) are counted and logged
    at DEBUG so operators can distinguish "empty dataset" from "every sample
    was skipped".
    """

    if not getattr(request.config, "response_only", False):
        return aggregate_response_only_boundaries([])
    if request.dataset_format != "chat_messages":
        return aggregate_response_only_boundaries([])
    if train_set is None:
        return aggregate_response_only_boundaries([])
    process = getattr(train_set, "process", None)
    try:
        sample_count = len(train_set)
    except TypeError:
        return aggregate_response_only_boundaries([])
    if process is None or sample_count == 0:
        return aggregate_response_only_boundaries([])

    skip_counter = {"count": 0}

    def _iter_boundaries() -> Any:
        for index in range(sample_count):
            try:
                sample = train_set[index]
                processed = process(sample)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                # Tools-only turns, custom roles, or samples MLX-LM chooses to
                # skip fall through to the next sample. MLX-LM still handles
                # them correctly at training time; we just cannot summarize.
                skip_counter["count"] += 1
                _PROBE_LOGGER.debug(
                    "response_only_boundary probe skipped sample %d: %s",
                    index,
                    exc,
                )
                continue
            if processed is None:
                skip_counter["count"] += 1
                continue
            try:
                tokens, offset = processed[0], processed[1]
            except (IndexError, TypeError):
                skip_counter["count"] += 1
                continue
            try:
                total = len(tokens)
            except TypeError:
                skip_counter["count"] += 1
                continue
            if total <= 0:
                skip_counter["count"] += 1
                continue
            yield ResponseOnlyBoundary(
                assistant_offset=int(offset),
                total_tokens=int(total),
            )

    aggregate = aggregate_response_only_boundaries(
        _iter_boundaries(),
        max_seq_length=getattr(request.config, "max_seq_length", None),
    )
    if skip_counter["count"]:
        _PROBE_LOGGER.debug(
            "response_only_boundary probe skipped %d / %d samples",
            skip_counter["count"],
            sample_count,
        )
    return aggregate


def _validate_response_only_trainable_tokens(
    request: TrainingRequest,
    aggregate: ResponseOnlyBoundaryAggregate,
) -> None:
    """Fail before MLX-LM when response-only masking leaves no labels."""

    if not getattr(request.config, "response_only", False):
        return
    if not getattr(request.config, "mask_prompt", False):
        return
    if request.dataset_format != "chat_messages":
        return
    if aggregate.sample_count <= 0:
        return
    if aggregate.trainable_response_token_count > 0:
        return
    affected_sample_count = (
        aggregate.fully_truncated_response_sample_count
        if aggregate.fully_truncated_response_sample_count > 0
        else aggregate.sample_count
    )
    max_seq_length = _positive_int(getattr(request.config, "max_seq_length", 0))
    boundary_max = _positive_int(getattr(aggregate, "boundary_max", 0))
    suggested_minimum = max(boundary_max + 1, max_seq_length + 1)
    raise ModelOperationError(
        code="response_only_labels_truncated",
        message=(
            "Response-only LoRA training would have zero trainable response "
            f"tokens after max_seq_length={request.config.max_seq_length} "
            "truncation. Increase max_seq_length, shorten the system prompt, "
            "or disable response-only masking."
        ),
        details={
            "field": "max_length",
            "reason": "no_unmasked_completion_tokens",
            "http_status": "422",
            "sample_count": str(aggregate.sample_count),
            "affected_sample_count": str(affected_sample_count),
            "requested_sequence_length": str(request.config.max_seq_length),
            "effective_sequence_length": str(request.config.max_seq_length),
            "suggested_minimum_sequence_length": str(suggested_minimum),
            "corrective_action": (
                "Increase max_seq_length, shorten the prompt/context before the assistant response, "
                "or disable response-only masking."
            ),
            "max_seq_length": str(request.config.max_seq_length),
            "response_only_boundary_sample_count": str(aggregate.sample_count),
            "response_only_boundary_min": str(aggregate.boundary_min),
            "response_only_boundary_max": str(aggregate.boundary_max),
            "response_only_boundary_mean": f"{aggregate.boundary_mean:.3f}",
            "response_only_response_tokens_mean": f"{aggregate.response_tokens_mean:.3f}",
            "response_only_trainable_response_token_count": str(
                aggregate.trainable_response_token_count
            ),
            "response_only_fully_truncated_response_sample_count": str(
                aggregate.fully_truncated_response_sample_count
            ),
        },
    )


_MEDIA_TOKEN_TOTAL_HINT_FIELDS = (
    "media_token_count",
    "media_tokens",
    "media_token_length",
)
_MEDIA_TOKEN_MODALITY_HINT_FIELDS = (
    "image_token_count",
    "video_token_count",
    "audio_token_count",
)
_MEDIA_TOKEN_HINT_FIELDS = (
    *_MEDIA_TOKEN_TOTAL_HINT_FIELDS,
    *_MEDIA_TOKEN_MODALITY_HINT_FIELDS,
)


def _validate_media_token_truncation(request: TrainingRequest) -> None:
    """Fail before MLX-LM when media-token hints cannot fit max_seq_length."""

    if request.dataset_format != "chat_messages":
        return
    max_seq_length = int(getattr(request.config, "max_seq_length", 0) or 0)
    if max_seq_length <= 0:
        return
    train_path = request.normalized_dataset_dir / "train.jsonl"
    if not train_path.is_file():
        return

    for sample_index, sample in _iter_jsonl_samples(train_path):
        media_token_count = _sample_media_token_count(sample)
        if media_token_count < max_seq_length:
            continue
        raise ModelOperationError(
            code="training_tokens_truncated",
            message=(
                "LoRA training media tokens would consume the configured "
                f"max_seq_length={max_seq_length} before any text supervision "
                "can fit. Increase max_seq_length or reduce media tokens before training."
            ),
            details={
                "field": "max_length",
                "reason": "media_tokens_truncated",
                "http_status": "422",
                "sample_index": str(sample_index),
                "affected_sample_count": "1",
                "requested_sequence_length": str(max_seq_length),
                "effective_sequence_length": str(max_seq_length),
                "media_token_count": str(media_token_count),
                "suggested_minimum_sequence_length": str(media_token_count + 1),
                "corrective_action": (
                    "Increase max_seq_length or reduce media tokens before training."
                ),
                "max_seq_length": str(max_seq_length),
            },
        )


def _iter_jsonl_samples(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield index, payload


def _sample_media_token_count(sample: dict[str, Any]) -> int:
    sample_total = _direct_media_token_hint(sample)
    if sample_total > 0:
        return sample_total

    total = 0
    total += _media_refs_token_count(sample.get("media_refs"))

    messages = sample.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            total += _direct_media_token_hint(message)
            total += _media_refs_token_count(message.get("media_refs"))
    return total


def _direct_media_token_hint(payload: dict[str, Any]) -> int:
    for field in _MEDIA_TOKEN_TOTAL_HINT_FIELDS:
        count = _positive_int(payload.get(field))
        if count > 0:
            return count
    return sum(_positive_int(payload.get(field)) for field in _MEDIA_TOKEN_MODALITY_HINT_FIELDS)


def _media_refs_token_count(media_refs: Any) -> int:
    if not isinstance(media_refs, list):
        return 0
    total = 0
    for media_ref in media_refs:
        if not isinstance(media_ref, dict):
            continue
        total += _direct_media_token_hint(media_ref)
    return total


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _maybe_chunk_training_dataset(
    request: TrainingRequest,
    tokenizer: Any,
) -> ChunkStats:
    """Rewrite train.jsonl with chunked samples when chunked_training is on.

    Non-destructive: the caller-supplied ``train.jsonl`` is preserved as
    ``train.jsonl.source`` on first invocation and re-read from that source
    on every subsequent rerun. The chunked output is materialized to
    ``train.jsonl`` so MLX-LM's ``load_local_dataset`` finds it by its
    canonical name. Re-running with a different ``chunk_size`` therefore
    operates on the original samples, not a previously-chunked view.

    Disabled by default — returns a stats object with enabled=False and zero
    counts so the caller can forward the values unconditionally into
    TrainingMetrics without branching.
    """

    config = request.config
    if not config.chunked_training:
        return ChunkStats(
            enabled=False,
            chunk_size=0,
            chunk_count=0,
            source_sample_count=0,
        )

    train_path = request.normalized_dataset_dir / "train.jsonl"
    source_path = request.normalized_dataset_dir / "train.jsonl.source"
    if not train_path.is_file() and not source_path.is_file():
        raise ModelOperationError(
            code="invalid_dataset_package",
            message=(
                f"chunked_training=true but train.jsonl is missing at "
                f"{train_path}."
            ),
        )
    # Preserve the pre-chunking source on first run; re-read from it on
    # every subsequent rerun so chunk_size changes operate on the original.
    if not source_path.is_file():
        train_path.rename(source_path)

    def _stream_samples():
        with source_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                yield json.loads(line)

    chunked_samples, stats = chunk_long_samples(
        _stream_samples(),
        chunk_size=config.chunk_size,
        tokenizer=tokenizer,
    )
    with train_path.open("w", encoding="utf-8") as handle:
        for sample in chunked_samples:
            handle.write(json.dumps(sample))
            handle.write("\n")
    return stats


def _reset_mlx_peak_memory_probe() -> None:
    try:
        import mlx.core as mx
    except ModuleNotFoundError:
        return
    try:
        if hasattr(mx, "metal") and hasattr(mx.metal, "reset_peak_memory"):
            mx.metal.reset_peak_memory()
    except Exception:
        return


def _mlx_peak_memory_gb() -> float:
    try:
        import mlx.core as mx
    except ModuleNotFoundError:
        return 0.0
    try:
        if hasattr(mx, "metal") and hasattr(mx.metal, "get_peak_memory"):
            peak_memory_bytes = float(mx.metal.get_peak_memory() or 0.0)
            if peak_memory_bytes > 0.0:
                return peak_memory_bytes / float(1024**3)
    except Exception:
        return 0.0
    return 0.0


def _checkpoint_summary(adapter_output_dir: Path) -> tuple[int, str]:
    checkpoint_candidates: dict[str, Path] = {}
    root_path = os.fspath(adapter_output_dir)
    root_weights_path = os.path.join(root_path, "adapters.safetensors")
    stack = [root_path]
    while stack:
        current_root = stack.pop()
        try:
            with os.scandir(current_root) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.name.endswith(".safetensors"):
                        continue
                    if entry.path == root_weights_path:
                        continue
                    relative_path = os.path.relpath(entry.path, root_path)
                    first_part = relative_path.split(os.sep, 1)[0]
                    if first_part != relative_path:
                        checkpoint_candidates.setdefault(first_part, Path(entry.path))
                        continue
                    checkpoint_candidates.setdefault(os.path.splitext(entry.name)[0], Path(entry.path))
        except FileNotFoundError:
            continue

    if not checkpoint_candidates:
        return 0, ""

    latest_checkpoint_path = max(
        checkpoint_candidates.values(),
        key=_checkpoint_order_key,
    )
    return len(checkpoint_candidates), str(latest_checkpoint_path)


def _checkpoint_order_key(path: Path) -> tuple[int, str]:
    path_text = str(path)
    numeric_tokens = _NUMERIC_TOKEN_RE.findall(path_text)
    return (int(numeric_tokens[-1]) if numeric_tokens else -1, path_text)


def _serialize_activation_request(request: ActivationRequest) -> dict:
    return {
        "job_id": request.job_id,
        "base_model_id": request.base_model_id,
        "model_path": str(request.model_path),
        "adapter_dir": str(request.adapter_dir),
        "adapter_manifest_path": str(request.adapter_manifest_path),
        "derived_model_dir": str(request.derived_model_dir),
        "activation_mode": request.activation_mode,
    }


def _deserialize_activation_request(payload: dict) -> ActivationRequest:
    return ActivationRequest(
        job_id=str(payload["job_id"]),
        base_model_id=str(payload["base_model_id"]),
        model_path=Path(payload["model_path"]),
        adapter_dir=Path(payload["adapter_dir"]),
        adapter_manifest_path=Path(payload["adapter_manifest_path"]),
        derived_model_dir=Path(payload["derived_model_dir"]),
        activation_mode=str(payload["activation_mode"]),
    )


def _serialize_activation_result(result: ActivationResult) -> dict:
    return {
        "derived_model_dir": str(result.derived_model_dir),
        "manifest_path": str(result.manifest_path),
        "metrics": asdict(result.metrics),
        "execution_backend": result.execution_backend,
    }


def _deserialize_activation_result(payload: dict) -> ActivationResult:
    return ActivationResult(
        derived_model_dir=Path(payload["derived_model_dir"]),
        manifest_path=Path(payload["manifest_path"]),
        metrics=ActivationMetrics(**payload["metrics"]),
        execution_backend=str(payload["execution_backend"]),
    )


def _run_train_cli(payload_path: Path) -> None:
    request = _deserialize_training_request(json.loads(payload_path.read_text(encoding="utf-8")))
    result = MLXLMRunner().train_native(request)
    print(_RESULT_PREFIX + json.dumps(_serialize_training_result(result), sort_keys=True))


def _run_activate_cli(payload_path: Path) -> None:
    request = _deserialize_activation_request(json.loads(payload_path.read_text(encoding="utf-8")))
    result = MLXLMRunner().activate_native(request)
    print(_RESULT_PREFIX + json.dumps(_serialize_activation_result(result), sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Melix MLX-LM runner wrapper.")
    parser.add_argument("command", choices=["train", "activate"])
    parser.add_argument("payload_path")
    args = parser.parse_args(argv)
    payload_path = Path(args.payload_path).resolve()

    if args.command == "train":
        _run_train_cli(payload_path)
        return 0

    _run_activate_cli(payload_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
