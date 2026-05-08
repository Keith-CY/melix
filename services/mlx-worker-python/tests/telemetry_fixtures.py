from __future__ import annotations

from worker.productization.apple_silicon_telemetry import (
    AppleSiliconProcessSample,
    AppleSiliconTelemetryCollector,
    AppleSiliconTelemetrySample,
)


class FixtureAppleSiliconSampler:
    def sample(self, *, sample_index: int) -> AppleSiliconTelemetrySample:
        return AppleSiliconTelemetrySample(
            timestamp_unix_ms=1_700_000_000_000 + sample_index,
            sample_index=sample_index,
            started_at_monotonic_ms=10_000 + sample_index,
            cpu_utilization_percent=42.0 + sample_index,
            p_core_utilization_percent=55.0,
            e_core_utilization_percent=22.0,
            gpu_utilization_percent=31.0,
            gpu_frequency_mhz=900.0,
            cpu_power_w=7.5,
            gpu_power_w=3.25,
            ane_power_w=1.5,
            dram_power_w=2.0,
            system_power_w=15.0,
            memory_used_bytes=8_000_000_000,
            memory_total_bytes=32_000_000_000,
            thermal_state="nominal",
            processes=(
                AppleSiliconProcessSample(
                    pid=100,
                    name="MelixControlPlane",
                    role="control_plane",
                    memory_bytes=50_000_000,
                    cpu_percent=4.0,
                ),
                AppleSiliconProcessSample(
                    pid=101,
                    name="melix-mlx-worker",
                    role="worker",
                    memory_bytes=150_000_000,
                    cpu_percent=12.0,
                ),
                AppleSiliconProcessSample(
                    pid=102,
                    name="mlx-runtime",
                    role="primary_runtime",
                    memory_bytes=500_000_000,
                    cpu_percent=82.0,
                ),
            ),
        )


def fixture_telemetry_collector(*, sample_count: int = 1) -> AppleSiliconTelemetryCollector:
    return AppleSiliconTelemetryCollector(
        sampler=FixtureAppleSiliconSampler(),
        sample_interval_s=0.0,
        sample_count=sample_count,
        join_timeout_s=1.0,
    )
