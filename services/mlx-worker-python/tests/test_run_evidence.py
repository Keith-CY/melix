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
    build_benchmark_stage_probes,
    build_evaluation_stage_probes,
    default_telemetry_summary,
    git_identity,
    summarize_run_evidence_probes,
    summarize_probe_timeline,
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


def test_benchmark_stage_probes_record_parent_child_runtime_and_fallback_phases() -> None:
    probes = build_benchmark_stage_probes(
        run_id="bench-1",
        trace_id="bench-1:trace",
        parent_span_id="bench-1:worker_dispatch",
        started_at_monotonic_ms=100,
        rows=[
            {
                "job_id": "bench-1",
                "suite": "smoke",
                "context_length": 16,
                "generation_length": 8,
                "batch_size": 1,
                "dataset_materialize_ms": 1.0,
                "prompt_render_ms": 2.0,
                "warmup_ms": 3.0,
                "prefill_ms": 4.0,
                "decode_ms": 5.0,
                "cache_hit": True,
                "speculative_fallback_count": 1,
            }
        ],
    )

    phases = [probe.phase for probe in probes]
    assert phases == [
        "cache_lookup",
        "dataset_materialize",
        "prompt_render",
        "cache_restore",
        "prefill",
        "decode",
        "fallback_enter",
    ]
    assert {probe.parent_span_id for probe in probes} == {"bench-1:worker_dispatch"}
    assert probes[-1].attributes["fallback_count"] == 1
    summary = summarize_probe_timeline(probes)
    assert summary["probe_count"] == 7
    assert summary["fallback_phases"][0]["phase"] == "fallback_enter"


def test_evaluation_stage_probes_record_failed_and_skipped_phases() -> None:
    probes = build_evaluation_stage_probes(
        run_id="eval-1",
        trace_id="eval-1:trace",
        parent_span_id="eval-1:worker_dispatch",
        started_at_monotonic_ms=200,
        samples=[
            {
                "job_id": "eval-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_id": "sample-1",
                "sample_render_ms": 1.0,
                "inference_ms": 8.0,
                "extraction_ms": 0.0,
                "validation_ms": 0.0,
                "scoring_ms": 0.0,
                "failure_stage": "extraction",
                "failure_reason": "parse_error",
            }
        ],
    )

    statuses_by_phase = {probe.phase: probe.status for probe in probes}
    assert statuses_by_phase["sample_select"] == "completed"
    assert statuses_by_phase["decode"] == "completed"
    assert statuses_by_phase["aggregate_result"] == "failed"
    assert statuses_by_phase["row_execute"] == "skipped"
    summary = summarize_probe_timeline(probes)
    assert summary["failed_phases"][0]["phase"] == "aggregate_result"
    assert summary["skipped_phases"][0]["phase"] == "row_execute"


def test_evaluation_stage_probes_bound_large_sample_details() -> None:
    samples = []
    for sample_index in range(100):
        sample = {
            "job_id": "eval-large",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_id": f"sample-{sample_index}",
            "sample_render_ms": 1.0,
            "inference_ms": float(sample_index),
            "extraction_ms": 2.0,
            "validation_ms": 3.0,
            "scoring_ms": 4.0,
        }
        if sample_index == 3:
            sample.update(
                {
                    "extraction_ms": 0.0,
                    "validation_ms": 0.0,
                    "scoring_ms": 0.0,
                    "failure_stage": "extraction",
                    "failure_reason": "parse_error",
                }
            )
        elif sample_index == 4:
            sample["failure_stage"] = "fallback"
        elif sample_index == 5:
            sample["scoring_ms"] = 0.0
        samples.append(sample)

    probes = build_evaluation_stage_probes(
        run_id="eval-large",
        trace_id="eval-large:trace",
        parent_span_id="eval-large:worker_dispatch",
        started_at_monotonic_ms=500,
        samples=samples,
        sample_limit=4,
        top_n=2,
        anomaly_limit=2,
    )

    aggregate_decode = next(
        probe
        for probe in probes
        if probe.phase == "decode"
        and probe.attributes.get("probe_kind") == "aggregate_summary"
    )
    assert aggregate_decode.duration_ms == 4950.0
    assert aggregate_decode.attributes["sample_count"] == 100
    assert aggregate_decode.attributes["duration_mean_ms"] == 49.5

    detail_selects = [
        probe
        for probe in probes
        if probe.phase == "sample_select"
        and probe.attributes.get("probe_kind") == "sample_detail"
    ]
    assert len(detail_selects) == 4
    reason_labels = {
        str(probe.attributes.get("sample_probe_reason", ""))
        for probe in detail_selects
    }
    assert any("failed" in label for label in reason_labels)
    assert any("fallback" in label for label in reason_labels)
    assert any("skipped" in label for label in reason_labels)
    assert any("top_duration" in label for label in reason_labels)
    assert len(probes) == 32

    summary = summarize_probe_timeline(probes)
    assert summary["component_duration_ms"]["runtime"] == pytest.approx(4950.001)
    assert summary["failed_phases"][0]["attributes"]["sample_id"] == "sample-3"
    assert summary["fallback_phases"][0]["attributes"]["probe_kind"] == "aggregate_summary"


def test_evaluation_stage_probe_sampling_env_can_disable_sample_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MELIX_EVALUATION_PROBE_SAMPLE_LIMIT", "0")
    monkeypatch.setenv("MELIX_EVALUATION_PROBE_TOP_N", "10")
    monkeypatch.setenv("MELIX_EVALUATION_PROBE_ANOMALY_LIMIT", "10")

    probes = build_evaluation_stage_probes(
        run_id="eval-env",
        trace_id="eval-env:trace",
        parent_span_id="eval-env:worker_dispatch",
        started_at_monotonic_ms=700,
        samples=[
            {
                "sample_id": "sample-failed",
                "sample_render_ms": 1.0,
                "inference_ms": 2.0,
                "extraction_ms": 0.0,
                "validation_ms": 0.0,
                "scoring_ms": 0.0,
                "failure_stage": "extraction",
            }
        ],
    )

    assert all(probe.attributes.get("probe_kind") != "sample_detail" for probe in probes)
    aggregate = next(
        probe
        for probe in probes
        if probe.phase == "aggregate_result"
        and probe.attributes.get("probe_kind") == "aggregate_summary"
    )
    assert aggregate.attributes["failed_count"] == 1
    assert aggregate.status == "failed"


def test_stage_probe_helpers_scrub_attributes_and_handle_invalid_values() -> None:
    benchmark_probes = build_benchmark_stage_probes(
        run_id="bench-edge",
        trace_id="bench-edge:trace",
        parent_span_id="bench-edge:worker_dispatch",
        started_at_monotonic_ms=10,
        rows=[
            {
                "job_id": "bench-edge",
                "suite": "smoke",
                "context_length": 16,
                "generation_length": 8,
                "batch_size": 1,
                "cache_hit": "yes",
                "warmup_ms": "not-a-number",
                "prefill_ms": 2.0,
                "decode_ms": 3.0,
                "speculative_fallback_count": 1,
                "dflash_rollback_count": object(),
                "runtime_kind": ["mlx", object(), "metal"],
                "runtime_name": {"safe": "runtime", "drop": object()},
            }
        ],
    )

    cache_probe = benchmark_probes[0]
    assert cache_probe.attributes["cache_hit"] is True
    assert cache_probe.attributes["runtime_kind"] == ["mlx", "metal"]
    assert cache_probe.attributes["runtime_name"] == {"safe": "runtime"}
    assert [probe.phase for probe in benchmark_probes][-1] == "fallback_enter"
    assert benchmark_probes[-1].attributes["fallback_count"] == 1

    evaluation_probes = build_evaluation_stage_probes(
        run_id="eval-fallback",
        trace_id="eval-fallback:trace",
        parent_span_id="eval-fallback:worker_dispatch",
        started_at_monotonic_ms=20,
        samples=[
            {
                "job_id": "eval-fallback",
                "suite_id": "mmlu",
                "sample_id": "sample-fallback",
                "sample_render_ms": {},
                "inference_ms": 4.0,
                "extraction_ms": 0.0,
                "validation_ms": 0.0,
                "scoring_ms": 0.0,
                "failure_stage": "fallback",
            }
        ],
    )

    assert [probe.phase for probe in evaluation_probes][-1] == "fallback_enter"


def test_probe_summary_ignores_malformed_run_evidence_payloads() -> None:
    summary = summarize_run_evidence_probes(
        [
            ["not", "a", "payload"],
            {
                "run_id": "run-with-probes",
                "run_kind": "evaluation",
                "probe_timeline": [
                    {
                        "run_id": "run-with-probes",
                        "trace_id": "run-with-probes:trace",
                        "span_id": "run-with-probes:decode",
                        "parent_span_id": "",
                        "component": "runtime",
                        "phase": "decode",
                        "started_at_monotonic_ms": 1,
                        "duration_ms": 2.0,
                        "status": "completed",
                        "attributes": {},
                    },
                    "not-a-probe",
                ],
            },
        ]
    )

    assert summary["probe_count"] == 1
    assert summary["runs"][0]["run_id"] == "run-with-probes"


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
