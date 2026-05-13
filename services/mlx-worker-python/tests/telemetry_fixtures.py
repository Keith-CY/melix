from __future__ import annotations

import subprocess
import threading
import tracemalloc

import pytest

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


def guard_production_safe_probe_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_heavy_sample(*args: object, **kwargs: object) -> None:
        raise AssertionError("production-safe probe policy must not call the heavy telemetry sampler")

    def fail_sleep(*args: object, **kwargs: object) -> None:
        raise AssertionError("production-safe probe policy must not sleep during persist")

    def fail_thread_start(self: threading.Thread) -> None:
        raise AssertionError("production-safe probe policy must not start a telemetry thread")

    original_subprocess_run = subprocess.run

    def fail_powermetrics(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
        command = args[0] if args else kwargs.get("args")
        if "powermetrics" in str(command):
            raise AssertionError("production-safe probe policy must not call powermetrics")
        return original_subprocess_run(*args, **kwargs)

    def fail_tracemalloc_start(*args: object, **kwargs: object) -> None:
        raise AssertionError("production-safe probe policy must not start tracemalloc")

    monkeypatch.setattr(
        "worker.productization.apple_silicon_telemetry.MacOSAppleSiliconSampler.sample",
        fail_heavy_sample,
    )
    monkeypatch.setattr(
        "worker.productization.apple_silicon_telemetry.subprocess.run",
        fail_powermetrics,
    )
    monkeypatch.setattr("worker.productization.apple_silicon_telemetry.time.sleep", fail_sleep)
    monkeypatch.setattr(threading.Thread, "start", fail_thread_start)
    monkeypatch.setattr(tracemalloc, "start", fail_tracemalloc_start)
