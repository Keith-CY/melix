from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.productization.serving_diagnostics import (
    ServingDiagnosticsComparisonError,
    ServingDiagnosticsEvent,
    ServingDiagnosticsRequestSummary,
    ServingEvidenceRun,
    validate_prefill_chunk_size,
    write_baseline_accelerated_evidence,
    write_serving_diagnostics_bundle,
)


def test_serving_diagnostics_bundle_writes_stable_layout_and_prefill_fields(
    tmp_path: Path,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-1",
        task_kind="text-generation",
        model_id="mlx-community/Qwen3.5-9B-MLX-4bit",
        runtime_kind="mlx-text",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"temperature": 0.0, "top_p": 1.0, "top_k": 1},
        status="completed",
        finish_reason="stop",
        prompt_tokens=128,
        completion_tokens=32,
        prefill_chunk_size=64,
        prefill_ms=12.5,
        decode_ms=22.0,
        prompt_tps=256.0,
        generation_tps=42.0,
        prefill_tokens_per_second=256.0,
        cache_hit_tokens=96,
        cache_miss_tokens=32,
        cache_restored_tokens=64,
        cache_computed_tokens=64,
        memory_used_bytes=1024,
        memory_total_bytes=4096,
        peak_memory_bytes=2048,
    )
    event = ServingDiagnosticsEvent(
        request_id="req-1",
        phase="prefill",
        event_index=0,
        status="completed",
        duration_ms=12.5,
        attributes={"prefill_chunk_size": 64, "cache_hit_tokens": 96},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-1",
        invocation={"command": "melix serve --diagnostics diag-1"},
        effective_config={"runtime": {"mode": "baseline"}},
        model_refs={"model_id": summary.model_id, "snapshot": "snap-1"},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    bundle_root = tmp_path / "serving-diagnostics" / "diag-1"
    assert paths["bundle_root"] == bundle_root
    assert set(paths) == {
        "bundle_root",
        "manifest",
        "effective_config",
        "request_summary",
        "events",
    }

    manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.serving_diagnostics.manifest.v1"
    assert manifest["diagnostics_mode"] == "debug"
    assert manifest["artifacts"] == {
        "effective_config": "effective-config.json",
        "request_summary": "request-summary.json",
        "events": "events.jsonl",
    }
    assert manifest["public_performance_claim_eligible"] is False

    effective_config = json.loads((bundle_root / "effective-config.json").read_text(encoding="utf-8"))
    assert effective_config["runtime"]["mode"] == "baseline"

    request_payload = json.loads((bundle_root / "request-summary.json").read_text(encoding="utf-8"))
    assert request_payload["prefill_chunk_size"] == 64
    assert request_payload["prefill_tokens_per_second"] == 256.0
    assert request_payload["prompt_tps"] == 256.0
    assert request_payload["generation_tps"] == 42.0
    assert request_payload["cache_hit_tokens"] == 96
    assert request_payload["cache_miss_tokens"] == 32
    assert request_payload["cache_restored_tokens"] == 64
    assert request_payload["cache_computed_tokens"] == 64
    assert request_payload["finish_reason"] == "stop"

    event_rows = [
        json.loads(line)
        for line in (bundle_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert event_rows == [
        {
            "schema_version": "melix.serving_diagnostics.event.v1",
            "request_id": "req-1",
            "phase": "prefill",
            "event_index": 0,
            "status": "completed",
            "duration_ms": 12.5,
            "attributes": {"cache_hit_tokens": 96, "prefill_chunk_size": 64},
        }
    ]


def test_serving_diagnostics_summary_defaults_throughput_to_float_zero() -> None:
    payload = ServingDiagnosticsRequestSummary(
        request_id="req-idle",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    ).to_dict()

    assert payload["prompt_tps"] == 0.0
    assert payload["generation_tps"] == 0.0
    assert isinstance(payload["prompt_tps"], float)
    assert isinstance(payload["generation_tps"], float)


@pytest.mark.parametrize("value", (0, -1, "0", "bad", None))
def test_validate_prefill_chunk_size_rejects_invalid_overrides(value: object) -> None:
    with pytest.raises(ValueError, match="prefill_chunk_size"):
        validate_prefill_chunk_size(value)


def test_validate_prefill_chunk_size_accepts_positive_integer_string() -> None:
    assert validate_prefill_chunk_size("128") == 128


def test_baseline_accelerated_evidence_requires_same_protocol_and_greedy_sampler(
    tmp_path: Path,
) -> None:
    baseline = _evidence_run(
        run_id="baseline",
        acceleration_mode="baseline",
        acceleration_admitted=False,
        fallback_reason="",
    )
    accelerated = _evidence_run(
        run_id="accelerated",
        acceleration_mode="sparse_prefill",
        acceleration_admitted=True,
        fallback_reason="",
        metrics={"prefill_ms": 7.0, "decode_ms": 20.0},
    )

    paths = write_baseline_accelerated_evidence(
        output_root=tmp_path,
        comparison_id="cmp-1",
        baseline=baseline,
        accelerated=accelerated,
    )

    payload = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "melix.serving_diagnostics.comparison.v1"
    assert payload["comparison_validity"] == "valid"
    assert payload["methodology"] == {
        "prompt_protocol_id": "chat.completions.v1",
        "prompt_digest": "sha256:prompt",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "effective_temperature": 0.0,
        "effective_top_p": 1.0,
        "effective_top_k": 1,
        "sampler_is_greedy": True,
        "tier_stability_status": "stable",
    }
    assert payload["runs"]["accelerated"]["acceleration_admitted"] is True
    assert payload["runs"]["accelerated"]["fallback_reason"] == ""
    prefill_row = next(row for row in payload["phase_rows"] if row["phase"] == "prefill")
    assert prefill_row["baseline"] == 10.0
    assert prefill_row["accelerated"] == 7.0
    assert prefill_row["delta"] == -3.0

    with pytest.raises(ServingDiagnosticsComparisonError, match="prompt_protocol_id"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-mismatch",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-mismatch",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                prompt_protocol_id="responses.v1",
            ),
        )

    with pytest.raises(ServingDiagnosticsComparisonError, match="greedy"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-nongreedy",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-nongreedy",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                effective_temperature=0.7,
            ),
        )


def _evidence_run(
    *,
    run_id: str,
    acceleration_mode: str,
    acceleration_admitted: bool,
    fallback_reason: str = "",
    prompt_protocol_id: str = "chat.completions.v1",
    effective_temperature: float = 0.0,
    metrics: dict[str, float] | None = None,
) -> ServingEvidenceRun:
    return ServingEvidenceRun(
        run_id=run_id,
        model_id="melix-dev-text",
        task_kind="text-generation",
        prompt_protocol_id=prompt_protocol_id,
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"max_output_tokens": 32},
        acceleration_mode=acceleration_mode,
        acceleration_admitted=acceleration_admitted,
        fallback_reason=fallback_reason,
        effective_temperature=effective_temperature,
        effective_top_p=1.0,
        effective_top_k=1,
        tier_stability_status="stable",
        metrics=metrics or {"prefill_ms": 10.0, "decode_ms": 20.0},
    )
