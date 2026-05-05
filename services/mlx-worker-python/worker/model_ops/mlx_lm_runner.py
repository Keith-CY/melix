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
from typing import Any

from worker.model_ops.errors import ModelOperationError
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
    # Milestone #43 Phase 2: template-aware response-only boundary observability.
    # Populated for chat_messages datasets when response_only is requested. Zero
    # when the sample format doesn't support response-only masking.
    response_only_boundary_sample_count: int = 0
    response_only_boundary_min: int = 0
    response_only_boundary_max: int = 0
    response_only_boundary_mean: float = 0.0
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
    def train(self, request: TrainingRequest) -> TrainingResult:
        if (
            _requires_alignment_trainer(request.config)
            and not self.supports_alignment_training(request.config)
        ):
            raise _alignment_trainer_unavailable_error(request.config)
        try:
            result = self.train_native(request)
            return replace(result, execution_backend="native")
        except NativeExecutionUnavailable as exc:
            result = self.train_subprocess(request, exc)
            return replace(result, execution_backend="subprocess")

    def supports_alignment_training(self, config: LoRATrainingConfig) -> bool:
        return config.training_objective == "preference"

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

        model, tokenizer = load(str(request.model_path), lazy=False)
        args = _mlx_lora_namespace(request)
        # Phase 3B: when chunked_training is enabled, rewrite train.jsonl with
        # chunked samples before MLX-LM reads it. No-op otherwise; the
        # stats returned carry enabled=False + chunk_count=0 so they fall
        # through into forward-compatible defaults on TrainingMetrics.
        chunk_stats = _maybe_chunk_training_dataset(request, tokenizer)
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
        return TrainingResult(
            weights_path=request.adapter_output_dir / "adapters.safetensors",
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
                chunked_enabled=chunk_stats.enabled,
                chunk_count=chunk_stats.chunk_count,
                source_sample_count=chunk_stats.source_sample_count,
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
        if prefix_index > 0 and stdout[prefix_index - 1] not in {"\n", "\r"}:
            search_end = prefix_index
            continue
        line_end = len(stdout)
        newline_index = stdout.find("\n", prefix_index)
        carriage_index = stdout.find("\r", prefix_index)
        if newline_index >= 0:
            line_end = min(line_end, newline_index)
        if carriage_index >= 0:
            line_end = min(line_end, carriage_index)
        return json.loads(stdout[prefix_index + prefix_length:line_end])


def _mlx_lora_namespace(request: TrainingRequest):
    import types

    return types.SimpleNamespace(
        seed=0,
        train=True,
        data=str(request.normalized_dataset_dir),
        model=str(request.model_path),
        fine_tune_type=(
            "dora" if request.config.adapter_algorithm == "dora" else "lora"
        ),
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

    aggregate = aggregate_response_only_boundaries(_iter_boundaries())
    if skip_counter["count"]:
        _PROBE_LOGGER.debug(
            "response_only_boundary probe skipped %d / %d samples",
            skip_counter["count"],
            sample_count,
        )
    return aggregate


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
