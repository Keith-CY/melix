from __future__ import annotations

import json
from pathlib import Path

from worker.productization.gemma_e4b_profile_gate import (
    collect_gemma_e4b_profile_gate_evidence,
    default_passing_evidence,
    evaluate_gemma_e4b_profile_gate,
    evaluate_gemma_e4b_profile_gate_evidence,
)


def test_gemma_e4b_profile_gate_passes_supported_profile_and_ok_threshold() -> None:
    report = evaluate_gemma_e4b_profile_gate_evidence(default_passing_evidence())

    assert report["status"] == "passed"
    assert report["metrics"]["release_gate_passed"] == 1.0
    assert report["metrics"]["selected_profile_receipt_passed"] == 1.0
    assert report["metrics"]["profile_proof_satisfied"] == 1.0
    assert report["metrics"]["capability_receipt_supported"] == 1.0
    assert report["metrics"]["batch_size_evidence_present"] == 1.0
    assert report["metrics"]["benchmark_threshold_passed"] == 1.0
    assert report["failures"] == []
    assert evaluate_gemma_e4b_profile_gate(
        report,
        {"metrics": {"release_gate_passed": {"min": 1.0}}},
    ) == []


def test_gemma_e4b_profile_gate_fails_when_profile_receipt_is_unverified() -> None:
    evidence = default_passing_evidence()
    evidence["selected_profile"]["profile_receipt"] = {
        "profile_admission_status": "experimental_unverified",
        "verification_status": "missing",
        "proof_matrix_id": "",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["selected_profile_receipt_passed"] == 0.0
    assert report["metrics"]["profile_proof_satisfied"] == 0.0
    assert (
        "gemma_e4b_profile.selected_profile.profile_receipt.profile_admission_status "
        "is experimental_unverified"
    ) in report["failures"]
    assert (
        "gemma_e4b_profile.selected_profile.profile_receipt.verification_status is missing"
        in report["failures"]
    )


def test_gemma_e4b_profile_gate_fails_when_unsupported_route_is_selected() -> None:
    evidence = default_passing_evidence()
    evidence["unsupported_routes"][0] = {
        "route": "speculative_decode",
        "selected": True,
        "status": "selected",
        "reason": "",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["unsupported_selected_route_count"] == 1.0
    assert "gemma_e4b_profile.unsupported_routes.speculative_decode was selected" in report["failures"]


def test_gemma_e4b_profile_gate_fails_when_refusal_reason_is_missing() -> None:
    evidence = default_passing_evidence()
    evidence["unsupported_routes"][0] = {
        "route": "speculative_decode",
        "selected": False,
        "status": "blocked",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["unsupported_route_missing_reason_count"] == 1.0
    assert (
        "gemma_e4b_profile.unsupported_routes.speculative_decode refusal reason is missing"
        in report["failures"]
    )


def test_gemma_e4b_profile_gate_fails_on_invalid_comparison_or_threshold_regression() -> None:
    evidence = default_passing_evidence()
    evidence["benchmark"]["comparison_validity"] = {
        "status": "invalid",
        "peer_comparison_valid": False,
    }
    evidence["benchmark"]["threshold_status"] = {
        "status": "threshold_failed",
        "row_count": 2,
        "failure_count": 2,
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["comparison_validity_passed"] == 0.0
    assert report["metrics"]["benchmark_threshold_passed"] == 0.0
    assert report["metrics"]["benchmark_threshold_failure_count"] == 2.0
    assert "gemma_e4b_profile.benchmark.comparison_validity.status is invalid" in report["failures"]
    assert "gemma_e4b_profile.benchmark.threshold_status.status is threshold_failed" in report["failures"]


def test_gemma_e4b_profile_gate_fails_on_missing_acceleration_or_batch_evidence() -> None:
    evidence = default_passing_evidence()
    evidence["selected_profile"].pop("resolved_acceleration_mode")
    evidence["selected_profile"]["completion_batch_size"] = 0

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["acceleration_mode_resolved"] == 0.0
    assert report["metrics"]["batch_size_evidence_present"] == 0.0
    assert "gemma_e4b_profile.selected_profile acceleration mode evidence is missing" in report["failures"]
    assert "gemma_e4b_profile.selected_profile batch size evidence is missing" in report["failures"]


def test_gemma_e4b_profile_gate_accepts_optimized_profile_with_passing_proof() -> None:
    evidence = default_passing_evidence()
    evidence["selected_profile"]["requested_profile"] = "throughput"
    evidence["selected_profile"]["effective_profile"] = "throughput"
    evidence["selected_profile"]["profile_mode"] = "optimized"
    evidence["selected_profile"]["acceleration_mode"] = "speculative_decode"
    evidence["selected_profile"]["resolved_acceleration_mode"] = "speculative_decode"
    evidence["selected_profile"]["profile_receipt"] = {
        "profile_admission_status": "admitted",
        "verification_status": "passed",
        "proof_matrix_id": "gemma-e4b-throughput-proof-20260602",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "passed"
    assert report["metrics"]["selected_profile_receipt_passed"] == 1.0
    assert report["metrics"]["profile_proof_satisfied"] == 1.0


def test_gemma_e4b_profile_gate_rejects_not_required_proof_for_optimized_profile() -> None:
    evidence = default_passing_evidence()
    evidence["selected_profile"]["requested_profile"] = "throughput"
    evidence["selected_profile"]["effective_profile"] = "throughput"
    evidence["selected_profile"]["profile_mode"] = "optimized"
    evidence["selected_profile"]["profile_receipt"] = {
        "profile_admission_status": "admitted",
        "verification_status": "not_required",
        "proof_matrix_id": "",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["selected_profile_receipt_passed"] == 0.0
    assert (
        "gemma_e4b_profile.selected_profile.profile_receipt.verification_status "
        "not_required is only valid for the default baseline profile"
    ) in report["failures"]


def test_gemma_e4b_profile_gate_fails_on_mismatched_acceleration_and_bad_capability() -> None:
    evidence = default_passing_evidence()
    evidence["selected_profile"]["resolved_acceleration_mode"] = "baseline"
    evidence["selected_profile"]["acceleration_mode"] = "speculative_decode"
    evidence["selected_profile"]["capability_receipt"] = {
        "state": "unsupported",
        "unsupported_reason": "missing_draft_model",
    }

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)

    assert report["status"] == "failed"
    assert report["metrics"]["capability_receipt_supported"] == 0.0
    assert report["metrics"]["acceleration_mode_resolved"] == 0.0
    assert (
        "gemma_e4b_profile.selected_profile.capability_receipt.state is unsupported"
        in report["failures"]
    )
    assert (
        "gemma_e4b_profile.selected_profile.capability_receipt.unsupported_reason is missing_draft_model"
        in report["failures"]
    )
    assert (
        "gemma_e4b_profile.selected_profile.acceleration_mode speculative_decode resolved to baseline"
        in report["failures"]
    )


def test_gemma_e4b_profile_gate_ignores_malformed_routes_and_policy_entries() -> None:
    evidence = default_passing_evidence()
    evidence["unsupported_routes"].append("not-a-route")
    evidence["unsupported_routes"][1]["selected"] = "selected"

    report = evaluate_gemma_e4b_profile_gate_evidence(evidence)
    failures = evaluate_gemma_e4b_profile_gate(
        report,
        {
            "metrics": {
                "bad_rule": "ignored",
                "missing_metric": {"min": 1.0},
            }
        },
    )

    assert report["status"] == "failed"
    assert "gemma_e4b_profile.unsupported_routes.active_kv_quantized was selected" in failures
    assert "gemma_e4b_profile.missing_metric is missing" in failures


def test_gemma_e4b_profile_gate_evaluator_applies_policy_rules() -> None:
    report = evaluate_gemma_e4b_profile_gate_evidence(default_passing_evidence())
    report["metrics"]["unsupported_selected_route_count"] = 1.0

    failures = evaluate_gemma_e4b_profile_gate(
        report,
        {"metrics": {"unsupported_selected_route_count": {"max": 0.0}}},
    )

    assert failures == [
        "gemma_e4b_profile.unsupported_selected_route_count=1.00 exceeded maximum 0.00"
    ]


def test_gemma_e4b_profile_gate_evaluator_ignores_non_dict_policy() -> None:
    report = evaluate_gemma_e4b_profile_gate_evidence(default_passing_evidence())

    assert evaluate_gemma_e4b_profile_gate(report, "not-a-policy") == []


def test_collect_gemma_e4b_profile_gate_loads_persisted_evidence(tmp_path: Path) -> None:
    evidence = default_passing_evidence()
    gate_dir = tmp_path / "jobs" / "gemma_e4b_profile_gate"
    gate_dir.mkdir(parents=True)
    (gate_dir / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")

    report = collect_gemma_e4b_profile_gate_evidence(tmp_path / "jobs")

    assert report["status"] == "passed"
    assert report["metrics"]["release_gate_passed"] == 1.0


def test_collect_gemma_e4b_profile_gate_loads_legacy_path_and_malformed_payload(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "jobs" / "gemma-e4b-profile-gate.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(json.dumps(default_passing_evidence()), encoding="utf-8")

    legacy_report = collect_gemma_e4b_profile_gate_evidence(tmp_path / "jobs")
    assert legacy_report["status"] == "passed"

    legacy_path.write_text(json.dumps(["bad"]), encoding="utf-8")
    malformed_report = collect_gemma_e4b_profile_gate_evidence(tmp_path / "jobs")

    assert malformed_report["status"] == "failed"
    assert malformed_report["artifact_status"] == "malformed"

    legacy_path.write_text("{invalid_json", encoding="utf-8")
    invalid_report = collect_gemma_e4b_profile_gate_evidence(tmp_path / "jobs")

    assert invalid_report["status"] == "failed"
    assert invalid_report["artifact_status"] == "malformed"


def test_collect_gemma_e4b_profile_gate_fails_when_artifact_is_missing(tmp_path: Path) -> None:
    report = collect_gemma_e4b_profile_gate_evidence(tmp_path / "jobs")

    assert report["status"] == "failed"
    assert report["artifact_status"] == "missing"
    assert "gemma_e4b_profile artifact is missing" in report["failures"]
