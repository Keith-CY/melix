from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.mlx_lm_runner import (
    HeldoutEvaluationRequest,
    HeldoutEvaluationResult,
    MLXLMRunner,
)
from worker.model_ops.training_config import LoRATrainingConfig
from worker.model_ops.training_dataset import NormalizedDatasetSnapshot
from worker.model_ops.training_runtime_preflight import call_with_training_failure_cleanup


def float_ext(ext: dict[str, str], key: str) -> float:
    raw_value = (ext.get(key) or "").strip()
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
    include_baseline: bool = False,
) -> dict[str, Any]:
    if normalized_snapshot.test_path is None or normalized_snapshot.test_sample_count <= 0:
        receipt = {
            "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
            "status": "skipped",
            "reason": _skipped_reason(
                normalized_snapshot=normalized_snapshot,
                test_ratio=test_ratio,
            ),
            "test_ratio": test_ratio,
            "test_path": "",
            "sample_count": 0,
            "loss": None,
            "perplexity": None,
            "backend": "",
        }
        if include_baseline:
            # No held-out split exists, so the adapter pass was never attempted;
            # reuse the receipt's own skip reason instead of implying the
            # adapter evaluation ran and failed to finish.
            receipt.update(_baseline_not_run_fields(str(receipt["reason"])))
        return receipt

    heldout_request = HeldoutEvaluationRequest(
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
    try:
        result = call_with_training_failure_cleanup(
            lambda: runner.evaluate_heldout(heldout_request),
            details=runtime_failure_details,
        )
    except ModelOperationError as exc:
        receipt = {
            "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
            "status": "failed",
            "reason": "heldout_evaluation_failed",
            "test_ratio": test_ratio,
            "test_path": str(normalized_snapshot.test_path),
            "sample_count": normalized_snapshot.test_sample_count,
            "loss": None,
            "perplexity": None,
            "backend": "",
            "error_code": exc.code,
            "error_message": exc.message,
        }
        if include_baseline:
            receipt.update(_baseline_not_run_fields("adapter_evaluation_not_completed"))
        return receipt
    receipt = {
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
    if include_baseline:
        receipt.update(
            _baseline_comparison_fields(
                runner=runner,
                request=heldout_request,
                adapter_result=result,
                runtime_failure_details=runtime_failure_details,
            )
        )
    return receipt


def _baseline_not_run_fields(reason: str) -> dict[str, Any]:
    return {
        "baseline_status": "skipped",
        "baseline_reason": reason,
        "baseline_loss": None,
        "baseline_perplexity": None,
        "baseline_backend": "",
        "loss_delta": None,
        "perplexity_ratio": None,
    }


def _baseline_comparison_fields(
    *,
    runner: MLXLMRunner,
    request: HeldoutEvaluationRequest,
    adapter_result: HeldoutEvaluationResult,
    runtime_failure_details: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the plain base model on the same test split.

    A failed baseline pass never fails the adapter receipt: the adapter
    metrics stand on their own and the failure is recorded next to them.
    """
    baseline_request = replace(request, adapter_dir=None)
    try:
        baseline = call_with_training_failure_cleanup(
            lambda: runner.evaluate_heldout(baseline_request),
            details=runtime_failure_details,
        )
    except ModelOperationError as exc:
        return {
            "baseline_status": "failed",
            "baseline_reason": "baseline_evaluation_failed",
            "baseline_loss": None,
            "baseline_perplexity": None,
            "baseline_backend": "",
            "loss_delta": None,
            "perplexity_ratio": None,
            "baseline_error_code": exc.code,
            "baseline_error_message": exc.message,
        }
    perplexity_ratio = (
        baseline.perplexity / adapter_result.perplexity
        if adapter_result.perplexity and adapter_result.perplexity > 0
        else None
    )
    # A divergent loss overflows math.exp to inf on either pass; inf/inf is
    # NaN and inf/finite is inf — neither survives strict JSON serialization.
    if perplexity_ratio is not None and not math.isfinite(perplexity_ratio):
        perplexity_ratio = None
    return {
        "baseline_status": "completed",
        "baseline_reason": "",
        "baseline_loss": baseline.loss,
        "baseline_perplexity": baseline.perplexity,
        "baseline_backend": baseline.execution_backend,
        # Positive delta / ratio > 1 means the adapter beat the base model on
        # the held-out split.
        "loss_delta": baseline.loss - adapter_result.loss,
        "perplexity_ratio": perplexity_ratio,
    }


def _skipped_reason(
    *,
    normalized_snapshot: NormalizedDatasetSnapshot,
    test_ratio: float,
) -> str:
    if test_ratio > 0.0:
        reason = str(
            normalized_snapshot.manifest_payload.get("test_split_reason", "")
        ).strip()
        if reason:
            return reason
    return "test_split_not_requested"


def write_heldout_evaluation_receipt(
    *,
    output_dir: Path,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    receipt_path = output_dir / "train_lora.heldout_evaluation.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(receipt_path)}
