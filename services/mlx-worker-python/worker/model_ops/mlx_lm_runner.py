from __future__ import annotations

import argparse
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
from worker.model_ops.training_config import LoRATrainingConfig

_RESULT_PREFIX = "__MELIX_MLX_RESULT__="


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


class MLXLMRunner:
    def train(self, request: TrainingRequest) -> TrainingResult:
        try:
            result = self.train_native(request)
            return replace(result, execution_backend="native")
        except NativeExecutionUnavailable as exc:
            result = self.train_subprocess(request, exc)
            return replace(result, execution_backend="subprocess")

    def activate(self, request: ActivationRequest) -> ActivationResult:
        try:
            result = self.activate_native(request)
            return replace(result, execution_backend="native")
        except NativeExecutionUnavailable as exc:
            result = self.activate_subprocess(request, exc)
            return replace(result, execution_backend="subprocess")

    def train_native(self, request: TrainingRequest) -> TrainingResult:
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

        for line in reversed(process.stdout.splitlines()):
            if line.startswith(_RESULT_PREFIX):
                return json.loads(line.removeprefix(_RESULT_PREFIX))

        raise ModelOperationError(
            code=error_code,
            message="MLX subprocess completed without returning a structured result.",
        )


def _mlx_lora_namespace(request: TrainingRequest):
    import types

    return types.SimpleNamespace(
        seed=0,
        train=True,
        data=str(request.normalized_dataset_dir),
        model=str(request.model_path),
        fine_tune_type="lora",
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
    root_weights_path = adapter_output_dir / "adapters.safetensors"
    for weights_path in adapter_output_dir.rglob("*.safetensors"):
        if weights_path == root_weights_path:
            continue
        relative_path = weights_path.relative_to(adapter_output_dir)
        if len(relative_path.parts) > 1:
            checkpoint_candidates.setdefault(relative_path.parts[0], weights_path)
            continue
        checkpoint_candidates.setdefault(weights_path.stem, weights_path)

    if not checkpoint_candidates:
        return 0, ""

    latest_checkpoint_path = max(
        checkpoint_candidates.values(),
        key=_checkpoint_order_key,
    )
    return len(checkpoint_candidates), str(latest_checkpoint_path)


def _checkpoint_order_key(path: Path) -> tuple[int, str]:
    numeric_tokens = [int(token) for token in re.findall(r"\d+", str(path))]
    return (numeric_tokens[-1] if numeric_tokens else -1, str(path))


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
