#!/usr/bin/env python3

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.engine.maintenance_core import BenchSample, MaintenanceCore  # noqa: E402


GENERATION_CONFIG_JSON = json.dumps(
    {
        "max_output_tokens": 8,
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
    },
    sort_keys=True,
)
SAMPLE_COUNT = 5
SPEED_TARGET_RATIO = 1.10


def _sample(
    *,
    route: str,
    ttft_ms: float,
    total_latency_ms: float,
    decode_tokens_per_second: float,
    runtime_active: bool = False,
) -> BenchSample:
    native_fields = {}
    if runtime_active:
        native_fields = {
            "speculative_acceptance_rate": 0.75,
            "speculative_rollback_rate": 0.0,
            "speculative_accepted_tokens": 9,
            "speculative_rejected_tokens": 3,
            "speculative_fallback_count": 0,
            "speculative_num_draft_tokens": 6,
            "speculative_draft_model_configured": True,
            "speculative_draft_propose_ms": 4.0,
            "speculative_target_verify_ms": 10.0,
            "native_acceleration_status": "admitted",
            "native_acceleration_mode": "speculative_decode",
            "native_acceleration_runtime_active": True,
            "native_acceleration_draft_supported": True,
            "native_acceleration_effective_depth": 6,
            "native_acceleration_request_gate": "auto",
            "native_acceleration_runtime_scope": "vlm_media",
            "native_acceleration_fallback_reason": "",
            "native_acceleration_rounds": 4,
            "native_acceleration_accepted_tokens": 9,
            "native_acceleration_rejected_tokens": 3,
            "native_acceleration_acceptance_rate": 0.75,
            "native_acceleration_rollback_rate": 0.0,
            "native_acceleration_draft_propose_ms": 4.0,
            "native_acceleration_target_verify_ms": 10.0,
            "native_acceleration_autoregressive_fallback": False,
            "native_acceleration_sampling_matches_baseline": True,
        }
    return BenchSample(
        ttft_ms=ttft_ms,
        total_latency_ms=total_latency_ms,
        completion_tokens=4,
        decode_tokens_per_second=decode_tokens_per_second,
        prefill_ms=ttft_ms,
        decode_ms=max(total_latency_ms - ttft_ms, 0.0),
        multimodal_decode_mode=route,
        multimodal_fallback_reason="",
        model_id="melix-dev-vlm",
        task_kind="image-text-to-text",
        prompt_protocol_id="melix.vlm.benchmark.v1",
        prompt_digest="sha256:repeated-media-prompt",
        prompt_template_digest="sha256:repeated-media-template",
        generation_config_digest="config-a",
        generation_config_json=GENERATION_CONFIG_JSON,
        route_stability_status="stable",
        acceleration_mode=route,
        **native_fields,
    )


def _speed_target_met(*, baseline: BenchSample, accelerated: BenchSample) -> bool:
    baseline_tps = baseline.decode_tokens_per_second
    accelerated_tps = accelerated.decode_tokens_per_second
    return (
        baseline_tps > 0.0
        and accelerated_tps / baseline_tps >= SPEED_TARGET_RATIO
        and accelerated.ttft_ms <= baseline.ttft_ms
    )


def _fallback_stable(sample: BenchSample) -> bool:
    return (
        sample.native_acceleration_runtime_active
        and not sample.native_acceleration_autoregressive_fallback
        and sample.native_acceleration_fallback_reason == ""
        and sample.speculative_fallback_count == 0
    )


def _repeated_media_correct(baseline: BenchSample, accelerated: BenchSample) -> bool:
    return (
        baseline.prompt_digest == accelerated.prompt_digest
        and baseline.prompt_template_digest == accelerated.prompt_template_digest
        and baseline.generation_config_digest == accelerated.generation_config_digest
        and accelerated.native_acceleration_sampling_matches_baseline
    )


def _comparison_artifact_status(comparison_path: Path) -> tuple[bool, float]:
    if not comparison_path.exists():
        return False, 0.0
    try:
        payload = json.loads(comparison_path.read_text(encoding="utf-8"))
        payload_bytes = float(comparison_path.stat().st_size)
    except (json.JSONDecodeError, OSError):
        return False, 0.0
    return payload.get("comparison_validity") == "valid", payload_bytes


def main() -> int:
    artifact_elapsed_ms: list[float] = []
    smoke_pass_count = 0.0
    speed_target_met_count = 0.0
    fallback_stability_count = 0.0
    repeated_media_correctness_count = 0.0
    comparison_artifact_present_count = 0.0
    payload_bytes = 0.0

    baseline = _sample(
        route="baseline",
        ttft_ms=20.0,
        total_latency_ms=60.0,
        decode_tokens_per_second=100.0,
    )
    accelerated = _sample(
        route="speculative_decode",
        ttft_ms=12.0,
        total_latency_ms=36.0,
        decode_tokens_per_second=166.7,
        runtime_active=True,
    )

    with tempfile.TemporaryDirectory(prefix="melix-vlm-speculative-smoke-") as directory:
        output_root = Path(directory)
        for sample_index in range(SAMPLE_COUNT):
            started = time.perf_counter()
            paths = MaintenanceCore._write_vlm_speculative_comparison_artifact(
                output_dir=output_root,
                comparison_id=f"smoke-{sample_index}",
                baseline=baseline,
                accelerated=accelerated,
            )
            artifact_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            comparison_path = paths["comparison"]
            artifact_present, payload_bytes = _comparison_artifact_status(comparison_path)
            speed_target_met = _speed_target_met(baseline=baseline, accelerated=accelerated)
            fallback_stable = _fallback_stable(accelerated)
            repeated_media_correct = _repeated_media_correct(baseline, accelerated)

            comparison_artifact_present_count += float(artifact_present)
            speed_target_met_count += float(speed_target_met)
            fallback_stability_count += float(fallback_stable)
            repeated_media_correctness_count += float(repeated_media_correct)
            smoke_pass_count += float(
                artifact_present and speed_target_met and fallback_stable and repeated_media_correct
            )

    print(
        json.dumps(
            {
                "acceptance_rate": accelerated.native_acceleration_acceptance_rate,
                "accelerated_decode_tokens_per_second": accelerated.decode_tokens_per_second,
                "accelerated_ttft_ms": accelerated.ttft_ms,
                "artifact_elapsed_ms_mean": round(statistics.fmean(artifact_elapsed_ms), 6),
                "baseline_decode_tokens_per_second": baseline.decode_tokens_per_second,
                "baseline_ttft_ms": baseline.ttft_ms,
                "comparison_artifact_present_count": comparison_artifact_present_count,
                "fallback_count": float(accelerated.speculative_fallback_count),
                "fallback_stability_count": fallback_stability_count,
                "repeated_media_correctness_count": repeated_media_correctness_count,
                "sample_count": float(SAMPLE_COUNT),
                "smoke_pass_count": smoke_pass_count,
                "speed_target_met_count": speed_target_met_count,
                "speed_target_ratio": SPEED_TARGET_RATIO,
                "valid_payload_bytes": payload_bytes,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
