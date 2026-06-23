from __future__ import annotations

from types import SimpleNamespace

from worker.engine import maintenance_core as maintenance_core_module
from worker.engine.maintenance_core import MaintenanceCore


def test_benchmark_cache_counter_records_are_slot_backed() -> None:
    assert not hasattr(
        maintenance_core_module.BenchMetricSpec(
            suite="smoke",
            name="bench.smoke.cached_prompt_tokens",
            value=1.0,
            unit="tok",
        ),
        "__dict__",
    )
    assert not hasattr(
        maintenance_core_module.WorkSavedCacheCounters(
            cached_prompt_tokens=1,
        ),
        "__dict__",
    )
    assert not hasattr(
        maintenance_core_module.ImageBenchSample(
            latency_ms=1.0,
            artifact_publish_ms=0.5,
            output_bytes=16,
        ),
        "__dict__",
    )


def test_vlm_fast_path_bench_metrics_include_work_saved_cache_counters() -> None:
    assert (
        MaintenanceCore._probe_counter(
            SimpleNamespace(image_feature_cache_hits="invalid"),
            "image_feature_cache_hits",
            -1,
        )
        == -1
    )

    def sample_with_cache_counters(
        counters: maintenance_core_module.WorkSavedCacheCounters,
        *,
        ttft_ms: float,
        total_latency_ms: float,
        image_feature_cache_hits: int,
        image_feature_cache_misses: int,
    ) -> maintenance_core_module.BenchSample:
        return maintenance_core_module._bench_sample_with_cache_counters(
            counters,
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            completion_tokens=2,
            image_feature_cache_hits=image_feature_cache_hits,
            image_feature_cache_misses=image_feature_cache_misses,
        )

    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            sample_with_cache_counters(
                maintenance_core_module.WorkSavedCacheCounters(
                    cached_prompt_tokens=-1,
                    media_feature_cache_hits=-1,
                    media_feature_cache_misses=-1,
                    media_feature_encoder_calls_saved=-1,
                    media_feature_work_saved_bytes=-1,
                    image_feature_encoder_calls_saved=-1,
                    image_feature_work_saved_bytes=-1,
                ),
                ttft_ms=10.0,
                total_latency_ms=20.0,
                image_feature_cache_hits=-1,
                image_feature_cache_misses=-1,
            ),
            sample_with_cache_counters(
                maintenance_core_module.WorkSavedCacheCounters(
                    cached_prompt_tokens=4,
                    media_feature_cache_hits=2,
                    media_feature_cache_misses=3,
                    media_feature_encoder_calls_saved=2,
                    media_feature_work_saved_bytes=1024,
                    image_feature_encoder_calls_saved=2,
                    image_feature_work_saved_bytes=1024,
                ),
                ttft_ms=8.0,
                total_latency_ms=16.0,
                image_feature_cache_hits=2,
                image_feature_cache_misses=3,
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.cached_prompt_tokens"].value == 4.0
    assert metrics_by_name["bench.smoke.media_feature_cache_hits"].value == 2.0
    assert metrics_by_name["bench.smoke.media_feature_cache_misses"].value == 3.0
    assert metrics_by_name["bench.smoke.media_feature_encoder_calls_saved"].value == 2.0
    assert metrics_by_name["bench.smoke.media_feature_work_saved_bytes"].value == 1024.0
    assert metrics_by_name["bench.smoke.image_feature_cache_hits"].value == 2.0
    assert metrics_by_name["bench.smoke.image_feature_cache_misses"].value == 3.0
    assert metrics_by_name["bench.smoke.image_feature_encoder_calls_saved"].value == 2.0
    assert metrics_by_name["bench.smoke.image_feature_work_saved_bytes"].value == 1024.0
