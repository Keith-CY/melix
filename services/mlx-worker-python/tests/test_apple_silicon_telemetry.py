from __future__ import annotations

import json
import plistlib
import subprocess
import threading
import time
from pathlib import Path

import pytest

import worker.productization.apple_silicon_telemetry as telemetry_module
from worker.productization.apple_silicon_telemetry import (
    AppleSiliconProcessSample,
    AppleSiliconTelemetryCollector,
    AppleSiliconTelemetryError,
    AppleSiliconTelemetrySample,
    AppleSiliconTelemetryUnsupportedError,
    MacOSAppleSiliconSampler,
    summarize_process_attribution,
    summarize_samples,
)


class _TwoSampleSampler:
    def sample(self, *, sample_index: int) -> AppleSiliconTelemetrySample:
        return AppleSiliconTelemetrySample(
            timestamp_unix_ms=1_700_000_000_000 + sample_index,
            sample_index=sample_index,
            started_at_monotonic_ms=100 + sample_index * 10,
            cpu_utilization_percent=40.0 + sample_index * 20.0,
            p_core_utilization_percent=70.0,
            e_core_utilization_percent=20.0,
            gpu_utilization_percent=30.0,
            gpu_frequency_mhz=850.0 + sample_index * 50.0,
            cpu_power_w=8.0 + sample_index,
            gpu_power_w=4.0,
            ane_power_w=1.5,
            dram_power_w=2.0,
            system_power_w=18.0 + sample_index,
            memory_used_bytes=9_000_000_000 + sample_index,
            memory_total_bytes=32_000_000_000,
            thermal_state="nominal",
            processes=(
                AppleSiliconProcessSample(
                    pid=1,
                    name="MelixControlPlane",
                    role="control_plane",
                    memory_bytes=10_000,
                    cpu_percent=2.0,
                ),
                AppleSiliconProcessSample(
                    pid=2,
                    name="melix-mlx-worker",
                    role="worker",
                    memory_bytes=20_000,
                    cpu_percent=8.0,
                ),
                AppleSiliconProcessSample(
                    pid=3,
                    name="mlx-runtime",
                    role="primary_runtime",
                    memory_bytes=30_000 + sample_index,
                    cpu_percent=50.0,
                ),
            ),
        )


class _FailingSampler:
    def sample(self, *, sample_index: int) -> AppleSiliconTelemetrySample:
        raise AppleSiliconTelemetryError("powermetrics_failed:fixture")


class _BlockingSampler:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def sample(self, *, sample_index: int) -> AppleSiliconTelemetrySample:
        self.started.set()
        self.release.wait(timeout=1.0)
        return AppleSiliconTelemetrySample(
            timestamp_unix_ms=1_700_000_000_000,
            sample_index=sample_index,
            started_at_monotonic_ms=100,
            cpu_power_w=1.0,
        )


def test_collector_writes_apple_silicon_summary_and_time_series(tmp_path: Path) -> None:
    collector = AppleSiliconTelemetryCollector(
        sampler=_TwoSampleSampler(),
        sample_interval_s=0.0,
        sample_count=2,
    )

    collection = collector.collect_completed_run(
        artifact_root=tmp_path,
        run_id="bench-1",
        output_token_count=10,
    )

    rows = [
        json.loads(line)
        for line in collection.artifact_path.read_text(encoding="utf-8").splitlines()
    ]
    summary = collection.summary.to_dict()

    assert collection.artifact_path == tmp_path / "telemetry-samples.jsonl"
    assert len(rows) == 2
    assert summary["collector_status"] == "collected"
    assert summary["average_cpu_utilization_percent"] == 50.0
    assert summary["peak_gpu_frequency_mhz"] == 900.0
    assert summary["average_system_power_w"] == 18.5
    assert summary["watts_per_output_token"] == 1.85
    assert summary["process_attribution"]["primary_runtime_process"]["pid"] == 3
    assert [probe.phase for probe in collection.probes] == [
        "hardware_sample",
        "process_sample",
        "power_sample",
    ]
    assert {probe.status for probe in collection.probes} == {"completed"}


def test_collector_records_failures_without_synthesizing_zero_telemetry(tmp_path: Path) -> None:
    collector = AppleSiliconTelemetryCollector(
        sampler=_FailingSampler(),
        sample_interval_s=0.0,
        sample_count=1,
    )

    collection = collector.collect_completed_run(artifact_root=tmp_path, run_id="eval-1")
    summary = collection.summary.to_dict()
    failure_row = json.loads(collection.artifact_path.read_text(encoding="utf-8"))

    assert summary["collector_status"] == "failed"
    assert summary["telemetry_failures"] == ["powermetrics_failed:fixture"]
    assert "average_cpu_power_w" not in summary
    assert failure_row["sample_kind"] == "telemetry_failure"
    assert {probe.status for probe in collection.probes} == {"failed"}
    assert collection.probes[0].error_code == "powermetrics_failed:fixture"


def test_telemetry_session_samples_in_background(tmp_path: Path) -> None:
    sampler = _BlockingSampler()
    collector = AppleSiliconTelemetryCollector(
        sampler=sampler,
        sample_interval_s=0.0,
        sample_count=1,
    )

    started_at = time.perf_counter()
    session = collector.start_session(run_id="run-1")
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    assert elapsed_ms < 100.0
    assert sampler.started.wait(timeout=0.5)
    sampler.release.set()
    collection = session.finish(artifact_root=tmp_path)
    assert collection.summary.collector_status == "collected"


def test_telemetry_session_records_sampler_failure_and_join_timeout(tmp_path: Path) -> None:
    failing = AppleSiliconTelemetryCollector(
        sampler=_FailingSampler(),
        sample_interval_s=0.0,
        sample_count=1,
    )
    failed_session = failing.start_session(run_id="failed-run")
    failed = failed_session.finish(artifact_root=tmp_path / "failed")
    assert failed.summary.collector_status == "failed"
    assert failed.summary.telemetry_failures == ("powermetrics_failed:fixture",)

    blocking_sampler = _BlockingSampler()
    blocking = AppleSiliconTelemetryCollector(
        sampler=blocking_sampler,
        sample_interval_s=0.0,
        sample_count=1,
        join_timeout_s=0.001,
    )
    timeout_session = blocking.start_session(run_id="timeout-run")
    timeout_session.start()
    assert blocking_sampler.started.wait(timeout=0.5)
    timed_out = timeout_session.finish(artifact_root=tmp_path / "timeout")
    blocking_sampler.release.set()
    assert "apple_silicon_telemetry_sampler_join_timeout" in timed_out.summary.telemetry_failures


def test_telemetry_session_stops_before_second_sample(tmp_path: Path) -> None:
    blocking_sampler = _BlockingSampler()
    collector = AppleSiliconTelemetryCollector(
        sampler=blocking_sampler,
        sample_interval_s=0.25,
        sample_count=2,
    )

    session = collector.start_session(run_id="stop-run")
    assert blocking_sampler.started.wait(timeout=0.5)
    blocking_sampler.release.set()
    collection = session.finish(artifact_root=tmp_path)

    assert collection.summary.sample_count == 1


def test_process_attribution_separates_required_groups() -> None:
    sample = _TwoSampleSampler().sample(sample_index=0)

    attribution = summarize_process_attribution((sample,))

    assert attribution["control_plane_process"]["role"] == "control_plane"
    assert attribution["primary_runtime_process"]["role"] == "primary_runtime"
    assert attribution["worker_processes"][0]["role"] == "worker"
    assert "control_plane" in attribution["process_tree_summary"]["roles"]


def test_summary_preserves_partial_status_for_sample_level_failures() -> None:
    sample = AppleSiliconTelemetrySample(
        timestamp_unix_ms=1,
        sample_index=0,
        started_at_monotonic_ms=2,
        cpu_power_w=3.0,
        failures=("ioreg_failed:fixture",),
    )

    summary = summarize_samples(
        time_series_path="telemetry-samples.jsonl",
        samples=(sample,),
    ).to_dict()

    assert summary["collector_status"] == "partial"
    assert summary["telemetry_failures"] == ["ioreg_failed:fixture"]
    assert summary["average_cpu_power_w"] == 3.0


def test_macos_sampler_parses_powermetrics_memory_and_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(telemetry_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(telemetry_module, "_sysctl_int", lambda name, timeout_s: 32_000_000_000)
    powermetrics_payload = {
        "CPU Power": 8_000,
        "GPU Power": 4_000,
        "ANE Power": 1_000,
        "DRAM Power": 2_000,
        "System Power": 15_000,
        "CPU Average Active Residency": 45.0,
        "P-Cluster Active Residency": 55.0,
        "E-Cluster Active Residency": 25.0,
        "GPU Active Residency": 30.0,
        "GPU HW Active Frequency": 900.0,
        "Thermal Pressure": "nominal",
    }
    vm_stat_output = """Mach Virtual Memory Statistics: (page size of 4096 bytes)
Pages active:                               10.
Pages inactive:                             20.
Pages speculative:                          30.
Pages wired down:                           40.
Pages occupied by compressor:               50.
"""
    ps_output = "\n".join(
        [
            "1 0 2.0 1000 /Applications/Melix.app/Contents/MacOS/MelixControlPlane",
            "2 1 8.0 2000 /usr/local/bin/melix-mlx-worker",
            "3 1 80.0 3000 /usr/local/bin/mlx-runtime",
            "4 1 5.0 4000 /usr/local/bin/openai-provider",
            "bad row",
        ]
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "/usr/bin/powermetrics":
            return subprocess.CompletedProcess(command, 0, stdout=plistlib.dumps(powermetrics_payload), stderr=b"")
        if command[0] == "/usr/bin/vm_stat":
            return subprocess.CompletedProcess(command, 0, stdout=vm_stat_output, stderr="")
        if command[0] == "/bin/ps":
            return subprocess.CompletedProcess(command, 0, stdout=ps_output, stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run)

    sample = MacOSAppleSiliconSampler(command_timeout_s=0.1).sample(sample_index=0)

    assert sample.cpu_power_w == 8.0
    assert sample.gpu_power_w == 4.0
    assert sample.system_power_w == 15.0
    assert sample.memory_used_bytes == 614_400
    assert sample.memory_total_bytes == 32_000_000_000
    assert sample.thermal_state == "nominal"
    assert [process.role for process in sample.processes] == [
        "control_plane",
        "worker",
        "primary_runtime",
        "external_provider",
    ]
    assert sample.processes[0].bundle_prefix == "/Applications/Melix.app"


def test_macos_sampler_records_channel_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(telemetry_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(telemetry_module, "_sysctl_int", lambda name, timeout_s: None)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "/usr/bin/powermetrics":
            raise FileNotFoundError("powermetrics")
        if command[0] == "/usr/bin/vm_stat":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="vm denied")
        if command[0] == "/bin/ps":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="ps denied")
        raise AssertionError(command)

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run)

    sample = MacOSAppleSiliconSampler(command_timeout_s=0.1).sample(sample_index=0)

    assert sample.failures == (
        "powermetrics_unavailable:FileNotFoundError",
        "vm_stat_failed:vm denied",
        "ps_failed:ps denied",
    )
    assert sample.cpu_power_w is None


def test_macos_sampler_records_parse_and_timeout_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(telemetry_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(telemetry_module, "_sysctl_int", lambda name, timeout_s: None)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "/usr/bin/powermetrics":
            return subprocess.CompletedProcess(command, 0, stdout=b"not plist", stderr=b"")
        if command[0] == "/usr/bin/vm_stat":
            raise subprocess.TimeoutExpired(cmd=command, timeout=0.1)
        if command[0] == "/bin/ps":
            raise subprocess.TimeoutExpired(cmd=command, timeout=0.1)
        raise AssertionError(command)

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run)

    sample = MacOSAppleSiliconSampler(command_timeout_s=0.1).sample(sample_index=0)

    assert sample.failures == (
        "powermetrics_plist_parse_failed:InvalidFileException",
        "vm_stat_unavailable:TimeoutExpired",
        "ps_unavailable:TimeoutExpired",
    )


def test_macos_sampler_rejects_non_apple_silicon_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(telemetry_module.platform, "machine", lambda: "x86_64")

    with pytest.raises(AppleSiliconTelemetryUnsupportedError):
        MacOSAppleSiliconSampler(command_timeout_s=0.1).sample(sample_index=0)


def test_low_level_parsers_cover_malformed_system_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    vm_stat_output = """Mach Virtual Memory Statistics: (page size of 4096 bytes)
this line has no counter
Pages active: not-a-number.
Pages wired down: 1.
"""
    assert telemetry_module._parse_vm_stat_used_bytes(vm_stat_output) == 4096

    process_rows = "\n".join(
        [
            "bad 0 1.0 1000 /usr/local/bin/mlx-runtime",
            "5 0 not-cpu 1000 /usr/local/bin/mlx-runtime",
            "6 0 1.0 1000 /usr/local/bin/other",
        ]
    )
    assert list(telemetry_module._parse_process_samples(process_rows)) == []
    assert telemetry_module._numeric_probe([{"nested": [{"CPU Power": "12.5"}]}], ("cpu_power",)) == 12.5
    assert telemetry_module._float_or_none(object()) is None

    def fake_run_exception(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run_exception)
    assert telemetry_module._sysctl_int("hw.memsize", timeout_s=0.1) is None

    def fake_run_nonzero(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(command, 1, stdout="123", stderr="")

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run_nonzero)
    assert telemetry_module._sysctl_int("hw.memsize", timeout_s=0.1) is None

    def fake_run_bad_int(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(command, 0, stdout="bad", stderr="")

    monkeypatch.setattr(telemetry_module.subprocess, "run", fake_run_bad_int)
    assert telemetry_module._sysctl_int("hw.memsize", timeout_s=0.1) is None
