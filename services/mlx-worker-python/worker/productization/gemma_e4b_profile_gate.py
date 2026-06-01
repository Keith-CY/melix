from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "melix.gemma_e4b_profile_gate.v1"
DEFAULT_MODEL_ID = "unsloth/gemma-4-E4B-it-MLX-8bit"
PERSISTED_EVIDENCE_PATH = Path("gemma_e4b_profile_gate") / "evidence.json"

DEFAULT_GEMMA_E4B_PROFILE_GATE_POLICY: dict[str, dict[str, dict[str, float]]] = {
    "metrics": {
        "release_gate_passed": {"min": 1.0},
        "failure_count": {"max": 0.0},
        "selected_profile_receipt_passed": {"min": 1.0},
        "profile_proof_satisfied": {"min": 1.0},
        "capability_receipt_supported": {"min": 1.0},
        "acceleration_mode_resolved": {"min": 1.0},
        "batch_size_evidence_present": {"min": 1.0},
        "unsupported_selected_route_count": {"max": 0.0},
        "unsupported_route_missing_reason_count": {"max": 0.0},
        "comparison_validity_passed": {"min": 1.0},
        "benchmark_threshold_passed": {"min": 1.0},
        "benchmark_threshold_failure_count": {"max": 0.0},
    }
}

_SUPPORTED_CAPABILITY_STATES = {"supported", "capability_supported"}
_NO_UNSUPPORTED_REASON = {"", "none", "unsupported_reason_none"}
_ADMITTED_PROFILE_STATUS = {"admitted"}
_PASSED_VERIFICATION_STATUS = {"passed"}
_NOT_REQUIRED_VERIFICATION_STATUS = {"not_required"}
_REFUSED_ROUTE_STATUSES = {"blocked", "refused", "unsupported"}
_NOT_SELECTED_ROUTE_STATUSES = {"not_selected", "not-selected", "skipped"}


def default_passing_evidence() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": DEFAULT_MODEL_ID,
        "selected_profile": {
            "requested_profile": "balanced",
            "effective_profile": "balanced",
            "profile_mode": "default",
            "acceleration_mode": "baseline",
            "resolved_acceleration_mode": "baseline",
            "prefill_batch_size": 2,
            "completion_batch_size": 2,
            "profile_receipt": {
                "profile_admission_status": "admitted",
                "verification_status": "not_required",
                "proof_matrix_id": "",
            },
            "capability_receipt": {
                "state": "supported",
                "unsupported_reason": "none",
            },
        },
        "unsupported_routes": [
            {
                "route": "speculative_decode",
                "selected": False,
                "status": "blocked",
                "reason": "missing_draft_model",
            },
            {
                "route": "active_kv_quantized",
                "selected": False,
                "status": "not_selected",
            },
            {
                "route": "sparse_prefill",
                "selected": False,
                "status": "not_selected",
            },
            {
                "route": "accelerated_prefill",
                "selected": False,
                "status": "not_selected",
            },
        ],
        "benchmark": {
            "comparison_validity": {
                "status": "valid",
                "peer_comparison_valid": True,
            },
            "threshold_status": {
                "status": "ok",
                "row_count": 1,
                "failure_count": 0,
                "total_latency_threshold_pct": 25.0,
                "decode_throughput_threshold_pct": 25.0,
            },
        },
    }


def load_persisted_evidence(jobs_root: str | Path) -> dict[str, Any] | None:
    root = Path(jobs_root)
    for path in (
        root / PERSISTED_EVIDENCE_PATH,
        root / "gemma-e4b-profile-gate.json",
    ):
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"schema_version": SCHEMA_VERSION, "artifact_status": "malformed"}
            if isinstance(payload, dict):
                return payload
            return {"schema_version": SCHEMA_VERSION, "artifact_status": "malformed"}
    return None


def collect_gemma_e4b_profile_gate_evidence(jobs_root: str | Path) -> dict[str, Any]:
    evidence = load_persisted_evidence(jobs_root)
    if evidence is None:
        return evaluate_gemma_e4b_profile_gate_evidence(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_status": "missing",
                "model_id": DEFAULT_MODEL_ID,
            }
        )
    return evaluate_gemma_e4b_profile_gate_evidence(evidence)


def evaluate_gemma_e4b_profile_gate_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(evidence)
    metrics, failures = _evaluate_metrics_and_failures(normalized)
    metrics["failure_count"] = float(len(failures))
    metrics["release_gate_passed"] = 1.0 if not failures else 0.0
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed" if not failures else "failed",
        "artifact_status": str(normalized.get("artifact_status") or "present"),
        "model_id": str(normalized.get("model_id") or ""),
        "selected_profile": _as_dict(normalized.get("selected_profile")),
        "unsupported_routes": _as_list(normalized.get("unsupported_routes")),
        "benchmark": _as_dict(normalized.get("benchmark")),
        "metrics": metrics,
        "failures": failures,
    }


def evaluate_gemma_e4b_profile_gate(report: Any, policy: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(report, dict):
        return ["gemma_e4b_profile evidence is missing"]
    failures = [str(failure) for failure in _as_list(report.get("failures"))]
    metrics = _as_dict(report.get("metrics"))
    policy_dict = _as_dict(policy)
    rules = _as_dict(policy_dict.get("metrics")) or policy_dict
    for failure in _evaluate_metric_rules(metrics, rules):
        if failure not in failures:
            failures.append(failure)
    return failures


def _evaluate_metrics_and_failures(evidence: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    failures: list[str] = []
    selected_profile = _as_dict(evidence.get("selected_profile"))
    profile_receipt = _as_dict(selected_profile.get("profile_receipt"))
    capability_receipt = _as_dict(selected_profile.get("capability_receipt"))

    if str(evidence.get("artifact_status") or "present") != "present":
        failures.append("gemma_e4b_profile artifact is missing")

    requested_profile = _text(selected_profile.get("requested_profile"))
    effective_profile = _text(selected_profile.get("effective_profile"))
    if not requested_profile:
        failures.append("gemma_e4b_profile.selected_profile.requested_profile is missing")
    if not effective_profile:
        failures.append("gemma_e4b_profile.selected_profile.effective_profile is missing")

    admission_status = _normalized_text(profile_receipt.get("profile_admission_status"))
    verification_status = _normalized_text(profile_receipt.get("verification_status"))
    proof_matrix_id = _text(profile_receipt.get("proof_matrix_id"))
    profile_mode = _normalized_text(
        selected_profile.get("profile_mode") or profile_receipt.get("profile_mode")
    )
    acceleration_mode = _normalized_text(selected_profile.get("acceleration_mode"))
    resolved_acceleration_mode = _normalized_text(selected_profile.get("resolved_acceleration_mode"))
    proof_not_required = (
        verification_status in _NOT_REQUIRED_VERIFICATION_STATUS
        and profile_mode == "default"
        and acceleration_mode == "baseline"
        and resolved_acceleration_mode == "baseline"
    )
    proof_satisfied = (
        verification_status in _PASSED_VERIFICATION_STATUS
        and bool(proof_matrix_id)
    ) or proof_not_required
    profile_receipt_passed = (
        admission_status in _ADMITTED_PROFILE_STATUS
        and proof_satisfied
    )
    if admission_status not in _ADMITTED_PROFILE_STATUS:
        failures.append(
            "gemma_e4b_profile.selected_profile.profile_receipt.profile_admission_status "
            f"is {admission_status or 'missing'}"
        )
    if (
        verification_status not in _PASSED_VERIFICATION_STATUS
        and verification_status not in _NOT_REQUIRED_VERIFICATION_STATUS
    ):
        failures.append(
            "gemma_e4b_profile.selected_profile.profile_receipt.verification_status "
            f"is {verification_status or 'missing'}"
        )
    if verification_status in _NOT_REQUIRED_VERIFICATION_STATUS and not proof_not_required:
        failures.append(
            "gemma_e4b_profile.selected_profile.profile_receipt.verification_status "
            "not_required is only valid for the default baseline profile"
        )
    if verification_status in _PASSED_VERIFICATION_STATUS and not proof_matrix_id:
        failures.append("gemma_e4b_profile.selected_profile.profile_receipt.proof_matrix_id is missing")

    capability_state = _normalized_text(capability_receipt.get("state"))
    unsupported_reason = _normalized_text(capability_receipt.get("unsupported_reason"))
    capability_supported = (
        capability_state in _SUPPORTED_CAPABILITY_STATES
        and unsupported_reason in _NO_UNSUPPORTED_REASON
    )
    if capability_state not in _SUPPORTED_CAPABILITY_STATES:
        failures.append(
            "gemma_e4b_profile.selected_profile.capability_receipt.state "
            f"is {capability_state or 'missing'}"
        )
    if unsupported_reason not in _NO_UNSUPPORTED_REASON:
        failures.append(
            "gemma_e4b_profile.selected_profile.capability_receipt.unsupported_reason "
            f"is {unsupported_reason}"
        )

    acceleration_mode_resolved = (
        bool(acceleration_mode)
        and bool(resolved_acceleration_mode)
        and acceleration_mode == resolved_acceleration_mode
    )
    if not acceleration_mode or not resolved_acceleration_mode:
        failures.append("gemma_e4b_profile.selected_profile acceleration mode evidence is missing")
    elif acceleration_mode != resolved_acceleration_mode:
        failures.append(
            "gemma_e4b_profile.selected_profile.acceleration_mode "
            f"{acceleration_mode} resolved to {resolved_acceleration_mode}"
        )

    prefill_batch_size = _number(selected_profile.get("prefill_batch_size"))
    completion_batch_size = _number(selected_profile.get("completion_batch_size"))
    batch_size_evidence_present = prefill_batch_size >= 1.0 and completion_batch_size >= 1.0
    if not batch_size_evidence_present:
        failures.append("gemma_e4b_profile.selected_profile batch size evidence is missing")

    unsupported_selected_route_count = 0.0
    unsupported_route_refusal_count = 0.0
    unsupported_route_missing_reason_count = 0.0
    for route in _as_list(evidence.get("unsupported_routes")):
        if not isinstance(route, dict):
            continue
        route_name = _text(route.get("route")) or "unknown"
        route_status = _normalized_text(route.get("status"))
        route_selected = _bool(route.get("selected")) or route_status == "selected"
        route_reason = _text(route.get("reason"))
        if route_selected:
            unsupported_selected_route_count += 1.0
            failures.append(f"gemma_e4b_profile.unsupported_routes.{route_name} was selected")
        if route_status in _REFUSED_ROUTE_STATUSES:
            unsupported_route_refusal_count += 1.0
            if not route_reason:
                unsupported_route_missing_reason_count += 1.0
                failures.append(
                    f"gemma_e4b_profile.unsupported_routes.{route_name} refusal reason is missing"
                )
        elif route_status not in _NOT_SELECTED_ROUTE_STATUSES:
            failures.append(
                f"gemma_e4b_profile.unsupported_routes.{route_name} status is {route_status or 'missing'}"
            )

    benchmark = _as_dict(evidence.get("benchmark"))
    comparison_validity = _as_dict(benchmark.get("comparison_validity"))
    comparison_validity_passed = (
        _normalized_text(comparison_validity.get("status")) == "valid"
        and comparison_validity.get("peer_comparison_valid") is True
    )
    if not comparison_validity_passed:
        failures.append(
            "gemma_e4b_profile.benchmark.comparison_validity.status "
            f"is {_normalized_text(comparison_validity.get('status')) or 'missing'}"
        )

    threshold_status = _as_dict(benchmark.get("threshold_status"))
    threshold_status_name = _normalized_text(threshold_status.get("status"))
    threshold_failure_count = _number(threshold_status.get("failure_count"))
    benchmark_threshold_passed = threshold_status_name == "ok" and threshold_failure_count == 0.0
    if not benchmark_threshold_passed:
        failures.append(
            "gemma_e4b_profile.benchmark.threshold_status.status "
            f"is {threshold_status_name or 'missing'}"
        )

    return (
        {
            "selected_profile_receipt_passed": 1.0 if profile_receipt_passed else 0.0,
            "profile_proof_satisfied": 1.0 if proof_satisfied else 0.0,
            "capability_receipt_supported": 1.0 if capability_supported else 0.0,
            "acceleration_mode_resolved": 1.0 if acceleration_mode_resolved else 0.0,
            "batch_size_evidence_present": 1.0 if batch_size_evidence_present else 0.0,
            "prefill_batch_size": prefill_batch_size,
            "completion_batch_size": completion_batch_size,
            "unsupported_selected_route_count": unsupported_selected_route_count,
            "unsupported_route_refusal_count": unsupported_route_refusal_count,
            "unsupported_route_missing_reason_count": unsupported_route_missing_reason_count,
            "comparison_validity_passed": 1.0 if comparison_validity_passed else 0.0,
            "benchmark_threshold_passed": 1.0 if benchmark_threshold_passed else 0.0,
            "benchmark_threshold_failure_count": threshold_failure_count,
            "benchmark_peer_delta_row_count": _number(threshold_status.get("row_count")),
        },
        failures,
    )


def _evaluate_metric_rules(metrics: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for metric_name, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        value = metrics.get(metric_name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"gemma_e4b_profile.{metric_name} is missing")
            continue
        numeric_value = float(value)
        if "min" in rule and numeric_value < float(rule["min"]):
            failures.append(
                f"gemma_e4b_profile.{metric_name}={numeric_value:.2f} "
                f"fell below minimum {float(rule['min']):.2f}"
            )
        if "max" in rule and numeric_value > float(rule["max"]):
            failures.append(
                f"gemma_e4b_profile.{metric_name}={numeric_value:.2f} "
                f"exceeded maximum {float(rule['max']):.2f}"
            )
    return failures


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalized_text(value: Any) -> str:
    return _text(value).lower().replace("-", "_")


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "selected"}
    return False
