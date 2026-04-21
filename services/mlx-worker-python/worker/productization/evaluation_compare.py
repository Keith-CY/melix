from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.productization.evaluation_schemas import (
    EvaluationCompareSample,
    EvaluationCompareSummary,
    EvaluationSample,
    build_evaluation_compare_sample_record,
    build_evaluation_compare_summary_record,
)
from worker.productization.statistical_evidence import (
    build_category_breakdown,
    build_paired_statistical_evidence,
    classify_release_verdict,
)

_ADAPTER_PACKAGE_SCHEMA_VERSION = "melix.lora_adapter_package.v1"


@dataclass(frozen=True)
class AdapterTargetSpec:
    """Adapter-manifest-backed compare target resolved from the request.

    Populated from a ``melix.lora_adapter_package.v1`` manifest. The
    ``ephemeral_derived_model_id`` follows the
    ``{source_model}-lora-{hash8}-compare-{job_id_suffix}`` pattern so
    concurrent compares on the same adapter get distinct ids and the
    transient catalog entry is visually distinct from a permanent adapter
    activation.
    """

    manifest_path: str
    adapter_set_hash: str
    adapter_weights_path: str
    derived_from_model_id: str
    derived_from_model_path: str
    ephemeral_derived_model_id: str

_DEFAULT_COMPARE_EFFECT_THRESHOLD = 0.1
_DEFAULT_COMPARE_CONFIDENCE_LEVEL = 0.95
_DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS = 400
_DEFAULT_COMPARE_BOOTSTRAP_SEED = 9


def parse_compare_target_model_ids(parameters: dict[str, str] | None) -> tuple[str, ...]:
    """Parse the comma-separated ``compare_target_model_ids`` request parameter.

    Module 2 allows mixing registered-model targets with adapter-manifest
    targets (see :func:`parse_compare_target_adapter_manifest_paths`), so
    empty lists are now permitted on this function — the caller is
    responsible for rejecting the case where BOTH parameters are empty.
    """
    raw_value = (parameters or {}).get("compare_target_model_ids", "")
    return tuple(
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    )


def parse_compare_target_adapter_manifest_paths(
    parameters: dict[str, str] | None,
) -> tuple[Path, ...]:
    """Parse the comma-separated ``compare_target_adapter_manifest_paths`` parameter.

    Each entry is expanded and resolved to an absolute path. Empty strings
    are filtered so an empty list is allowed — the caller decides whether
    zero adapter targets plus zero registered targets is an error.
    """
    raw_value = (parameters or {}).get("compare_target_adapter_manifest_paths", "")
    return tuple(
        Path(value.strip()).expanduser().resolve()
        for value in raw_value.split(",")
        if value.strip()
    )


def load_adapter_target_spec(
    *,
    manifest_path: Path,
    job_id: str,
) -> AdapterTargetSpec:
    """Read an adapter package manifest and build an ``AdapterTargetSpec``.

    Validates the manifest is a ``melix.lora_adapter_package.v1`` file and
    extracts the fields needed to materialize an ephemeral adapter-backed
    load via Module 1's runtime contract.
    """
    if not manifest_path.is_file():
        raise ValueError(f"Adapter compare target manifest missing: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Adapter compare target manifest is not valid JSON: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"Adapter compare target manifest must be a JSON object: {manifest_path}"
        )
    if payload.get("schema_version") != _ADAPTER_PACKAGE_SCHEMA_VERSION:
        raise ValueError(
            f"Adapter compare target is not a {_ADAPTER_PACKAGE_SCHEMA_VERSION} "
            f"package: {manifest_path}"
        )

    adapter_set_hash = str(payload.get("adapter_set_hash", "")).strip()
    weights_path = str(payload.get("weights_path", "")).strip()
    derived_from_model_id = str(payload.get("source_model", "")).strip()
    derived_from_model_path = str(payload.get("source_model_path", "")).strip()
    if not adapter_set_hash:
        raise ValueError(f"Adapter compare target missing adapter_set_hash: {manifest_path}")
    if not weights_path:
        raise ValueError(f"Adapter compare target missing weights_path: {manifest_path}")
    if not derived_from_model_id:
        raise ValueError(f"Adapter compare target missing source_model: {manifest_path}")

    # Ephemeral derived model id: distinct per adapter per job so concurrent
    # compares don't collide and operators watching the catalog can tell the
    # entry is transient (the "-compare-" segment is deliberately visible).
    job_suffix = job_id.split("-")[-1] if "-" in job_id else job_id
    ephemeral_derived_model_id = (
        f"{derived_from_model_id}-lora-{adapter_set_hash[:8]}-compare-{job_suffix}"
    )
    return AdapterTargetSpec(
        manifest_path=str(manifest_path),
        adapter_set_hash=adapter_set_hash,
        adapter_weights_path=weights_path,
        derived_from_model_id=derived_from_model_id,
        derived_from_model_path=derived_from_model_path,
        ephemeral_derived_model_id=ephemeral_derived_model_id,
    )


def resolve_compare_target_models(
    *,
    registry: Any | None,
    target_model_ids: tuple[str, ...],
) -> dict[str, Any]:
    if registry is None or hasattr(registry, "list_loaded_models") is False:
        raise ValueError("Evaluation compare requires a live registry with loaded target models.")
    if not target_model_ids:
        return {}
    loaded_models_by_id: dict[str, Any] = {}
    for handle in registry.list_loaded_models():
        loaded_model = registry.get_loaded_model(handle)
        if loaded_model is None:
            continue
        model_id = str(getattr(getattr(loaded_model, "spec", None), "model_id", "")).strip()
        if model_id and model_id not in loaded_models_by_id:
            loaded_models_by_id[model_id] = loaded_model
    unknown_targets = [model_id for model_id in target_model_ids if model_id not in loaded_models_by_id]
    if unknown_targets:
        raise ValueError(f"Unknown comparison target model IDs: {', '.join(unknown_targets)}")
    return {model_id: loaded_models_by_id[model_id] for model_id in target_model_ids}


def resolve_compare_target_adapters(
    *,
    registry: Any,
    adapter_target_specs: tuple[AdapterTargetSpec, ...],
) -> tuple[dict[str, Any], list[str]]:
    """Ephemerally load each adapter target via the registry.

    Returns ``({ephemeral_model_id: LoadedModel, ...}, [handle, ...])``. The
    caller is responsible for unloading each handle in a ``finally`` block so
    crashed compares don't leak transient catalog entries.

    Each target is loaded with ``runtime_mode=RUNTIME_MODE_ADAPTER_BACKED`` on
    the ModelSpec, which routes through Module 1's ``AutoMLXBackend.load_model``
    — MLX-LM applies the adapter via ``adapter_path`` at load time.
    """
    from packages.protocol.python.worker.v1 import common_pb2

    loaded_targets: dict[str, Any] = {}
    unload_handles: list[str] = []
    if not adapter_target_specs:
        return loaded_targets, unload_handles
    if registry is None or not hasattr(registry, "load_model"):
        raise ValueError(
            "Evaluation compare requires a live registry to materialize adapter targets."
        )
    for spec in adapter_target_specs:
        model_spec = common_pb2.ModelSpec(
            model_id=spec.ephemeral_derived_model_id,
            model_path=spec.derived_from_model_path,
            model_kind="text",
            runtime_mode=common_pb2.RUNTIME_MODE_ADAPTER_BACKED,
        )
        model_spec.ext["melix.activation_mode"] = "adapter_backed_runtime"
        model_spec.ext["melix.adapter_manifest_path"] = spec.manifest_path
        model_spec.ext["melix.adapter_weights_path"] = spec.adapter_weights_path
        model_spec.ext["melix.adapter_set_hash"] = spec.adapter_set_hash
        model_spec.ext["melix.derived_from_model_id"] = spec.derived_from_model_id
        model_spec.ext["melix.derived_from_adapter"] = "true"
        loaded = registry.load_model(model_spec)
        loaded_targets[spec.ephemeral_derived_model_id] = loaded
        unload_handles.append(getattr(loaded, "handle", ""))
    return loaded_targets, unload_handles


def build_compare_samples(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    target_model_id: str,
    threshold: float,
    base_samples: tuple[EvaluationSample, ...],
    target_samples: tuple[EvaluationSample, ...],
) -> tuple[EvaluationCompareSample, ...]:
    records: list[EvaluationCompareSample] = []
    for base_sample, target_sample in zip(base_samples, target_samples, strict=True):
        outcome = compare_outcome(
            base_typed_score=base_sample.typed_score,
            target_typed_score=target_sample.typed_score,
            base_validation_status=base_sample.validation_status,
            target_validation_status=target_sample.validation_status,
        )
        regression_kind = compare_regression_kind(
            threshold=threshold,
            base_sample=base_sample,
            target_sample=target_sample,
        )
        records.append(
            build_evaluation_compare_sample_record(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                sample_id=base_sample.sample_id,
                target_model_id=target_model_id,
                input_text=base_sample.input_text,
                target=base_sample.target,
                base_extracted_result=base_sample.extracted_result,
                target_extracted_result=target_sample.extracted_result,
                base_raw_response=base_sample.raw_response,
                target_raw_response=target_sample.raw_response,
                base_typed_score=base_sample.typed_score,
                target_typed_score=target_sample.typed_score,
                outcome=outcome,
                regression_kind=regression_kind,
                base_time_s=base_sample.time_s,
                target_time_s=target_sample.time_s,
                base_extraction_status=base_sample.extraction_status,
                target_extraction_status=target_sample.extraction_status,
                base_validation_status=base_sample.validation_status,
                target_validation_status=target_sample.validation_status,
                base_failure_reason=base_sample.failure_reason,
                target_failure_reason=target_sample.failure_reason,
                base_parse_status=base_sample.extraction_status,
                target_parse_status=target_sample.extraction_status,
                code_language=target_sample.code_language or base_sample.code_language,
                code_entry_point=target_sample.code_entry_point or base_sample.code_entry_point,
                base_code_compile_status=base_sample.code_compile_status,
                target_code_compile_status=target_sample.code_compile_status,
                base_code_runtime_status=base_sample.code_runtime_status,
                target_code_runtime_status=target_sample.code_runtime_status,
                base_code_timeout_status=base_sample.code_timeout_status,
                target_code_timeout_status=target_sample.code_timeout_status,
                base_code_test_status=base_sample.code_test_status,
                target_code_test_status=target_sample.code_test_status,
                base_code_tests_passed=base_sample.code_tests_passed,
                target_code_tests_passed=target_sample.code_tests_passed,
                base_code_tests_total=base_sample.code_tests_total,
                target_code_tests_total=target_sample.code_tests_total,
                base_code_failure_detail=base_sample.code_failure_detail,
                target_code_failure_detail=target_sample.code_failure_detail,
                category_label=base_sample.category_label or target_sample.category_label,
                subject_label=base_sample.subject_label or target_sample.subject_label,
            )
        )
    return tuple(records)


def build_compare_summary(
    *,
    job_id: str,
    base_model_id: str,
    target_model_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    threshold: float,
    base_samples: tuple[EvaluationSample, ...],
    compare_samples: tuple[EvaluationCompareSample, ...],
    effect_threshold: float = _DEFAULT_COMPARE_EFFECT_THRESHOLD,
    confidence_level: float = _DEFAULT_COMPARE_CONFIDENCE_LEVEL,
    bootstrap_iterations: int = _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
    bootstrap_seed: int = _DEFAULT_COMPARE_BOOTSTRAP_SEED,
    duration_seconds: float,
    report_path: str,
) -> EvaluationCompareSummary:
    win_count = sum(1 for sample in compare_samples if sample.outcome == "win")
    loss_count = sum(1 for sample in compare_samples if sample.outcome == "loss")
    tie_count = sum(1 for sample in compare_samples if sample.outcome == "tie")
    regression_count = sum(1 for sample in compare_samples if sample.regression_kind != "")
    base_accuracy = round(
        sum(
            1
            for sample in base_samples
            if sample.validation_status == "validated" and sample.typed_score >= threshold
        )
        / max(sample_size, 1),
        4,
    )
    target_accuracy = round(
        sum(
            1
            for sample in compare_samples
            if sample.target_validation_status == "validated" and sample.target_typed_score >= threshold
        )
        / max(sample_size, 1),
        4,
    )
    delta_accuracy = round(target_accuracy - base_accuracy, 4)
    base_typed_score_mean = round(
        sum(sample.typed_score for sample in base_samples) / max(sample_size, 1),
        4,
    )
    target_typed_score_mean = round(
        sum(sample.target_typed_score for sample in compare_samples) / max(sample_size, 1),
        4,
    )
    delta_typed_score_mean = round(target_typed_score_mean - base_typed_score_mean, 4)
    base_extraction_success_rate = round(
        sum(1 for sample in base_samples if sample.extraction_status == "extracted")
        / max(sample_size, 1),
        4,
    )
    target_extraction_success_rate = round(
        sum(1 for sample in compare_samples if sample.target_extraction_status == "extracted")
        / max(sample_size, 1),
        4,
    )
    base_validation_success_rate = round(
        sum(1 for sample in base_samples if sample.validation_status == "validated")
        / max(sample_size, 1),
        4,
    )
    target_validation_success_rate = round(
        sum(1 for sample in compare_samples if sample.target_validation_status == "validated")
        / max(sample_size, 1),
        4,
    )
    extraction_failure_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "extraction_failure"
    )
    validation_failure_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "validation_failure"
    )
    score_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "score_regression"
    )
    category_rows: tuple[dict[str, object], ...] = tuple(
        {
            "category_label": sample.category_label,
            "base_correct": (
                sample.base_validation_status == "validated" and sample.base_typed_score >= threshold
            ),
            "target_correct": (
                sample.target_validation_status == "validated" and sample.target_typed_score >= threshold
            ),
        }
        for sample in compare_samples
    )
    paired_outcomes = tuple(
        int(row["target_correct"]) - int(row["base_correct"])
        for row in category_rows
    )
    statistical_evidence = build_paired_statistical_evidence(
        paired_outcomes=paired_outcomes,
        confidence_level=confidence_level,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    release_gate_summary = classify_release_verdict(
        delta_accuracy=delta_accuracy,
        effect_threshold=effect_threshold,
        bootstrap_interval=dict(statistical_evidence.get("bootstrap", {})),
        analytical_interval=dict(statistical_evidence.get("analytical", {})),
    )
    category_breakdown = build_category_breakdown(rows=category_rows)
    return build_evaluation_compare_summary_record(
        job_id=job_id,
        base_model_id=base_model_id,
        target_model_id=target_model_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        win_count=win_count,
        loss_count=loss_count,
        tie_count=tie_count,
        regression_count=regression_count,
        base_accuracy=base_accuracy,
        target_accuracy=target_accuracy,
        delta_accuracy=delta_accuracy,
        effect_threshold=effect_threshold,
        verdict=str(release_gate_summary["verdict"]),
        category_breakdown=category_breakdown,
        statistical_evidence=statistical_evidence,
        release_gate_summary=release_gate_summary,
        duration_seconds=duration_seconds,
        metrics={
            "eval.compare.base_accuracy": base_accuracy,
            "eval.compare.delta_accuracy": delta_accuracy,
            "eval.compare.effect_threshold": float(effect_threshold),
            "eval.compare.base_typed_score_mean": base_typed_score_mean,
            "eval.compare.target_typed_score_mean": target_typed_score_mean,
            "eval.compare.delta_typed_score_mean": delta_typed_score_mean,
            "eval.compare.base_extraction_success_rate": base_extraction_success_rate,
            "eval.compare.target_extraction_success_rate": target_extraction_success_rate,
            "eval.compare.base_validation_success_rate": base_validation_success_rate,
            "eval.compare.target_validation_success_rate": target_validation_success_rate,
            "eval.compare.loss_count": float(loss_count),
            "eval.compare.regression_count": float(regression_count),
            "eval.compare.regression.extraction_failure_count": float(extraction_failure_regression_count),
            "eval.compare.regression.validation_failure_count": float(validation_failure_regression_count),
            "eval.compare.regression.score_count": float(score_regression_count),
            "eval.compare.target_accuracy": target_accuracy,
            "eval.compare.tie_count": float(tie_count),
            "eval.compare.win_count": float(win_count),
        },
        units={
            "eval.compare.base_accuracy": "ratio",
            "eval.compare.delta_accuracy": "ratio",
            "eval.compare.effect_threshold": "ratio",
            "eval.compare.base_typed_score_mean": "ratio",
            "eval.compare.target_typed_score_mean": "ratio",
            "eval.compare.delta_typed_score_mean": "ratio",
            "eval.compare.base_extraction_success_rate": "ratio",
            "eval.compare.target_extraction_success_rate": "ratio",
            "eval.compare.base_validation_success_rate": "ratio",
            "eval.compare.target_validation_success_rate": "ratio",
            "eval.compare.loss_count": "count",
            "eval.compare.regression_count": "count",
            "eval.compare.regression.extraction_failure_count": "count",
            "eval.compare.regression.validation_failure_count": "count",
            "eval.compare.regression.score_count": "count",
            "eval.compare.target_accuracy": "ratio",
            "eval.compare.tie_count": "count",
            "eval.compare.win_count": "count",
        },
        report_path=report_path,
    )
def compare_outcome(
    *,
    base_typed_score: float,
    target_typed_score: float,
    base_validation_status: str,
    target_validation_status: str,
) -> str:
    base_valid = base_validation_status == "validated"
    target_valid = target_validation_status == "validated"
    if target_valid and not base_valid:
        return "win"
    if base_valid and not target_valid:
        return "loss"
    if base_valid and target_valid:
        if target_typed_score > base_typed_score:
            return "win"
        if target_typed_score < base_typed_score:
            return "loss"
    return "tie"


def compare_regression_kind(
    *,
    threshold: float,
    base_sample: EvaluationSample,
    target_sample: EvaluationSample,
) -> str:
    base_valid = base_sample.validation_status == "validated"
    target_valid = target_sample.validation_status == "validated"
    if base_valid and not target_valid:
        if target_sample.extraction_status != "extracted":
            return "extraction_failure"
        return "validation_failure"
    if base_valid and target_valid and target_sample.typed_score < base_sample.typed_score:
        if base_sample.typed_score >= threshold or target_sample.typed_score < threshold:
            return "score_regression"
    return ""
