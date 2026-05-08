from __future__ import annotations

from pathlib import Path

import pytest

from worker.productization.run_evidence import (
    RUN_EVIDENCE_SCHEMA_VERSION,
    RunEvidenceArtifact,
    RunEvidenceEnvelope,
    RunEvidenceMetric,
    RunEvidenceProbe,
    RunEvidenceValidationError,
    assert_valid_run_evidence_payload,
    default_telemetry_summary,
    git_identity,
    validate_run_evidence_payload,
)


def test_run_evidence_roundtrips_completed_failed_cancelled_and_fallback_runs() -> None:
    for status in ("completed", "failed", "cancelled", "fallback"):
        evidence = _evidence(status=status)

        payload = evidence.to_dict()
        assert_valid_run_evidence_payload(payload)

        roundtripped = RunEvidenceEnvelope.from_dict(payload)
        assert roundtripped.to_dict() == payload
        assert payload["schema_version"] == RUN_EVIDENCE_SCHEMA_VERSION
        assert payload["probe_timeline"][0]["phase"] == "artifact_write"
        assert payload["telemetry_summary"]["collector_status"] == "not_collected"
        if status == "fallback":
            assert payload["fallback_summary"]["fallback_count"] == 1


@pytest.mark.parametrize(
    "field_name",
    ("run_id", "target_model_id", "probe_timeline", "telemetry_summary"),
)
def test_run_evidence_validator_rejects_missing_required_fields(field_name: str) -> None:
    payload = _evidence(status="completed").to_dict()
    payload.pop(field_name)

    with pytest.raises(RunEvidenceValidationError) as exc_info:
        assert_valid_run_evidence_payload(payload)

    assert f"missing required evidence field: {field_name}" in str(exc_info.value)


def test_run_evidence_validator_rejects_malformed_required_values() -> None:
    payload = _evidence(status="completed").to_dict()
    payload.update(
        {
            "schema_version": "old",
            "run_id": "",
            "dirty_worktree": "false",
            "runtime_config": [],
            "generation_config": [],
            "metrics": {},
            "probe_timeline": [],
            "telemetry_summary": [],
            "artifacts": [],
            "failure_summary": [],
            "fallback_summary": [],
        }
    )

    errors = validate_run_evidence_payload(payload)

    assert "schema_version must be melix.run_evidence.v1" in errors
    assert "required evidence field is empty: run_id" in errors
    assert "dirty_worktree must be boolean" in errors
    assert "runtime_config must be an object" in errors
    assert "generation_config must be an object" in errors
    assert "metrics must be a list" in errors
    assert "probe_timeline must be a non-empty list" in errors
    assert "telemetry_summary must be an object" in errors
    assert "artifacts must be a non-empty list" in errors
    assert "failure_summary must be an object" in errors
    assert "fallback_summary must be an object" in errors


def test_git_identity_prefers_environment_and_falls_back_when_git_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MELIX_GIT_COMMIT", "commit-from-env")
    monkeypatch.setenv("MELIX_GIT_BRANCH", "branch-from-env")
    monkeypatch.setenv("MELIX_GIT_DIRTY", "true")

    assert git_identity(tmp_path) == ("commit-from-env", "branch-from-env", True)

    monkeypatch.delenv("MELIX_GIT_COMMIT")
    monkeypatch.delenv("MELIX_GIT_BRANCH")
    monkeypatch.delenv("MELIX_GIT_DIRTY")

    assert git_identity(tmp_path) == ("unknown", "unknown", True)


def _evidence(*, status: str) -> RunEvidenceEnvelope:
    fallback_summary = {"fallback_count": 1, "fallbacks": ["provider_retry"]} if status == "fallback" else {}
    return RunEvidenceEnvelope(
        run_id=f"run-{status}",
        melix_commit="abc123",
        git_branch="main",
        dirty_worktree=False,
        run_kind="evaluation",
        started_at=100,
        ended_at=150,
        duration_ms=50,
        status=status,
        command="melix eval run",
        artifact_root="/tmp/melix/eval/run-1",
        target_model_id="melix-dev-text",
        hf_repo_id="HuggingFaceH4/ultrachat_200k",
        task_kind="text-generation",
        model_snapshot="snapshot-a",
        adapter_id="",
        adapter_snapshot="",
        runtime_kind="deterministic",
        runtime_config={"scoring_mode": "exact_match"},
        dataset_ref="mmlu.dev.v1",
        dataset_revision="main",
        suite_id="mmlu",
        sample_count=1,
        input_digest="input-sha",
        prompt_template_digest="prompt-sha",
        generation_config={"seed": 7},
        metrics=(
            RunEvidenceMetric(name="eval.mmlu.accuracy", value=1.0, unit="ratio"),
        ) if status == "completed" else (),
        probe_timeline=(
            RunEvidenceProbe(
                run_id=f"run-{status}",
                trace_id=f"run-{status}:trace",
                span_id=f"run-{status}:artifact_write",
                parent_span_id="",
                component="report",
                phase="artifact_write",
                started_at_monotonic_ms=10,
                duration_ms=2.5,
                status="completed",
                attributes={"artifact_count": 1},
            ),
        ),
        telemetry_summary=default_telemetry_summary(),
        artifacts=(
            RunEvidenceArtifact(
                kind="result",
                path="evaluation-result.json",
                role="result",
            ),
        ),
        failure_summary={"failed": status in {"failed", "cancelled"}, "status": status},
        fallback_summary=fallback_summary,
    )
