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


def _sample(
    *,
    route: str,
    prompt_digest: str = "sha256:prompt-a",
    fallback_reason: str = "",
    ttft_ms: float = 12.0,
    total_latency_ms: float = 36.0,
    decode_tokens_per_second: float = 166.7,
) -> BenchSample:
    return BenchSample(
        ttft_ms=ttft_ms,
        total_latency_ms=total_latency_ms,
        completion_tokens=4,
        decode_tokens_per_second=decode_tokens_per_second,
        prefill_ms=ttft_ms,
        decode_ms=max(total_latency_ms - ttft_ms, 0.0),
        multimodal_decode_mode=route,
        multimodal_fallback_reason=fallback_reason,
        model_id="melix-dev-vlm",
        task_kind="image-text-to-text",
        prompt_protocol_id="melix.vlm.benchmark.v1",
        prompt_digest=prompt_digest,
        prompt_template_digest="sha256:template-a",
        generation_config_digest="config-a",
        generation_config_json=GENERATION_CONFIG_JSON,
        route_stability_status="stable",
        acceleration_mode=route,
    )


def main() -> int:
    sample_count = 5
    valid_elapsed_ms: list[float] = []
    blocked_elapsed_ms: list[float] = []
    valid_payload_bytes = 0
    valid_status = 0.0
    blocked_status = 0.0
    identity_match = 0.0
    route_stability = 0.0
    baseline = _sample(
        route="single_stream",
        fallback_reason="image_batch1_step_backend_unsupported",
        ttft_ms=20.0,
        total_latency_ms=60.0,
        decode_tokens_per_second=100.0,
    )
    fast_path = _sample(route="image_batch1_step")
    mismatched_fast_path = _sample(
        route="image_batch1_step",
        prompt_digest="sha256:prompt-b",
    )
    with tempfile.TemporaryDirectory(prefix="melix-vlm-batch1-comparison-") as directory:
        output_root = Path(directory)
        for sample_index in range(sample_count):
            started = time.perf_counter()
            paths = MaintenanceCore._write_vlm_batch1_comparison_artifact(
                output_dir=output_root,
                comparison_id=f"valid-{sample_index}",
                baseline=baseline,
                fast_path=fast_path,
            )
            valid_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            payload = json.loads(paths["comparison"].read_text(encoding="utf-8"))
            valid_status += float(payload.get("comparison_validity") == "valid")
            valid_payload_bytes = paths["comparison"].stat().st_size

            started = time.perf_counter()
            metrics = MaintenanceCore._vlm_batch1_comparison_status_metrics(
                suite_id="smoke",
                valid=False,
                blocked=True,
                reason="prompt_digest must match for baseline-vs-accelerated evidence",
                baseline=baseline,
                fast_path=mismatched_fast_path,
            )
            blocked_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            by_name = {metric.name: metric.value for metric in metrics}
            blocked_status += by_name["bench.smoke.vlm_batch1_comparison_claim_blocked"]
            identity_match += by_name["bench.smoke.vlm_batch1_comparison_identity_match"]
            route_stability += by_name["bench.smoke.vlm_batch1_route_stability"]

    print(
        json.dumps(
            {
                "sample_count": float(sample_count),
                "valid_elapsed_ms_mean": round(statistics.fmean(valid_elapsed_ms), 6),
                "blocked_elapsed_ms_mean": round(statistics.fmean(blocked_elapsed_ms), 6),
                "valid_status_count": valid_status,
                "blocked_status_count": blocked_status,
                "identity_match_count": identity_match,
                "route_stability_count": route_stability,
                "valid_payload_bytes": float(valid_payload_bytes),
                "baseline_ttft_ms": baseline.ttft_ms,
                "fast_path_ttft_ms": fast_path.ttft_ms,
                "baseline_decode_tokens_per_second": baseline.decode_tokens_per_second,
                "fast_path_decode_tokens_per_second": fast_path.decode_tokens_per_second,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
