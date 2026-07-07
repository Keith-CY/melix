from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.mlx_lm_runner import HeldoutEvaluationRequest, MLXLMRunner
from worker.model_ops.training_config import LoRATrainingConfig
from worker.model_ops.training_dataset import NormalizedDatasetSnapshot
from worker.model_ops.training_runtime_preflight import call_with_training_failure_cleanup


def float_ext(ext: dict[str, str], key: str) -> float:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return 0.0
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{key} must be a number.",
            details={
                "field": key,
                "reason": "not_a_number",
                "received": raw_value,
                "http_status": "422",
            },
        ) from exc
    if 0.0 <= value < 1.0:
        return value
    raise ModelOperationError(
        code="invalid_argument",
        message=f"{key} must be greater than or equal to 0 and less than 1.",
        details={
            "field": key,
            "reason": "out_of_bounds",
            "received": raw_value,
            "allowed_bounds": "0 <= value < 1",
            "http_status": "422",
        },
    )


def evaluate_heldout_if_requested(
    *,
    runner: MLXLMRunner,
    job_id: str,
    source_model: common_pb2.ModelSpec,
    training_model_path: Path,
    adapter_output_dir: Path,
    normalized_snapshot: NormalizedDatasetSnapshot,
    config: LoRATrainingConfig,
    trainer_dataset_format: str,
    test_ratio: float,
    runtime_failure_details: dict[str, Any],
) -> dict[str, Any]:
    if normalized_snapshot.test_path is None or normalized_snapshot.test_sample_count <= 0:
        return {
            "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
            "status": "skipped",
            "reason": "test_split_not_requested",
            "test_ratio": test_ratio,
            "test_path": "",
            "sample_count": 0,
            "loss": None,
            "perplexity": None,
            "backend": "",
        }

    result = call_with_training_failure_cleanup(
        lambda: runner.evaluate_heldout(
            HeldoutEvaluationRequest(
                job_id=job_id,
                base_model_id=source_model.model_id,
                model_path=training_model_path,
                model_revision=source_model.revision,
                adapter_dir=adapter_output_dir,
                normalized_dataset_dir=normalized_snapshot.dataset_dir,
                config=config,
                dataset_format=trainer_dataset_format,
                test_sample_count=normalized_snapshot.test_sample_count,
                source_model_kind=source_model.model_kind,
                source_model_ext=dict(source_model.ext),
            )
        ),
        details=runtime_failure_details,
    )
    return {
        "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
        "status": "completed",
        "reason": "",
        "test_ratio": test_ratio,
        "test_path": str(normalized_snapshot.test_path),
        "sample_count": result.sample_count,
        "loss": result.loss,
        "perplexity": result.perplexity,
        "backend": result.execution_backend,
    }


def write_heldout_evaluation_receipt(
    *,
    output_dir: Path,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    receipt_path = output_dir / "train_lora.heldout_evaluation.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(receipt_path)}
