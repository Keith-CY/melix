from __future__ import annotations

import json
import os
import platform
import plistlib
import subprocess
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worker.productization.run_evidence import (
    RunEvidenceProbe,
    RunEvidenceTelemetrySummary,
)


APPLE_SILICON_TELEMETRY_SAMPLE_SCHEMA_VERSION = "melix.apple_silicon_telemetry_sample.v1"


class AppleSiliconTelemetryError(RuntimeError):
    pass


class AppleSiliconTelemetryUnsupportedError(AppleSiliconTelemetryError):
    pass


@dataclass(frozen=True)
class AppleSiliconProcessSample:
    pid: int
    name: str
    role: str
    port: int = 0
    bundle_prefix: str = ""
    memory_bytes: int | None = None
    cpu_percent: float | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "pid": self.pid,
            "name": self.name,
            "role": self.role,
            "port": self.port,
            "bundle_prefix": self.bundle_prefix,
        }
        if self.memory_bytes is not None:
            payload["memory_bytes"] = self.memory_bytes
        if self.cpu_percent is not None:
            payload["cpu_percent"] = round(self.cpu_percent, 4)
        return payload


@dataclass(frozen=True)
class AppleSiliconTelemetrySample:
    timestamp_unix_ms: int
    sample_index: int
    started_at_monotonic_ms: int
    cpu_utilization_percent: float | None = None
    p_core_utilization_percent: float | None = None
    e_core_utilization_percent: float | None = None
    gpu_utilization_percent: float | None = None
    gpu_frequency_mhz: float | None = None
    cpu_power_w: float | None = None
    gpu_power_w: float | None = None
    ane_power_w: float | None = None
    dram_power_w: float | None = None
    system_power_w: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    thermal_state: str = ""
    processes: tuple[AppleSiliconProcessSample, ...] = ()
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": APPLE_SILICON_TELEMETRY_SAMPLE_SCHEMA_VERSION,
            "timestamp_unix_ms": self.timestamp_unix_ms,
            "sample_index": self.sample_index,
            "started_at_monotonic_ms": self.started_at_monotonic_ms,
        }
        for key in _NUMERIC_SAMPLE_KEYS:
            value = getattr(self, key)
            if value is not None:
                payload[key] = round(float(value), 6)
        if self.memory_used_bytes is not None:
            payload["memory_used_bytes"] = self.memory_used_bytes
        if self.memory_total_bytes is not None:
            payload["memory_total_bytes"] = self.memory_total_bytes
        if self.thermal_state:
            payload["thermal_state"] = self.thermal_state
        if self.processes:
            payload["processes"] = [process.to_dict() for process in self.processes]
        if self.failures:
            payload["telemetry_failures"] = list(self.failures)
        return payload


@dataclass(frozen=True)
class AppleSiliconTelemetryCollection:
    summary: RunEvidenceTelemetrySummary
    samples: tuple[AppleSiliconTelemetrySample, ...]
    probes: tuple[RunEvidenceProbe, ...]
    artifact_path: Path


class AppleSiliconTelemetryCollector:
    def __init__(
        self,
        *,
        sampler: Any | None = None,
        sample_interval_s: float = 1.0,
        sample_count: int = 3,
        join_timeout_s: float = 4.0,
    ) -> None:
        self._sampler = sampler or MacOSAppleSiliconSampler()
        self._sample_interval_s = max(float(sample_interval_s), 0.0)
        self._sample_count = max(int(sample_count), 1)
        self._join_timeout_s = max(float(join_timeout_s), 0.0)

    def start_session(self, *, run_id: str) -> AppleSiliconTelemetrySession:
        session = AppleSiliconTelemetrySession(
            run_id=run_id,
            sampler=self._sampler,
            sample_interval_s=self._sample_interval_s,
            sample_count=self._sample_count,
            join_timeout_s=self._join_timeout_s,
        )
        session.start()
        return session

    def collect_completed_run(
        self,
        *,
        artifact_root: Path,
        run_id: str,
        output_token_count: int = 0,
    ) -> AppleSiliconTelemetryCollection:
        samples: list[AppleSiliconTelemetrySample] = []
        failures: list[str] = []
        for sample_index in range(self._sample_count):
            try:
                samples.append(self._sampler.sample(sample_index=sample_index))
            except AppleSiliconTelemetryError as exc:
                failures.append(str(exc))
                break
            if sample_index + 1 < self._sample_count:
                time.sleep(self._sample_interval_s)
        return _finalize_collection(
            artifact_root=artifact_root,
            run_id=run_id,
            samples=tuple(samples),
            failures=tuple(failures),
            output_token_count=output_token_count,
        )


class AppleSiliconTelemetrySession:
    def __init__(
        self,
        *,
        run_id: str,
        sampler: Any,
        sample_interval_s: float,
        sample_count: int,
        join_timeout_s: float,
    ) -> None:
        self._run_id = run_id
        self._sampler = sampler
        self._sample_interval_s = sample_interval_s
        self._sample_count = sample_count
        self._join_timeout_s = join_timeout_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._samples: list[AppleSiliconTelemetrySample] = []
        self._failures: list[str] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._sample_loop,
            name=f"melix-apple-silicon-telemetry-{self._run_id}",
            daemon=True,
        )
        self._thread.start()

    def finish(
        self,
        *,
        artifact_root: Path,
        output_token_count: int = 0,
    ) -> AppleSiliconTelemetryCollection:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._join_timeout_s)
            if thread.is_alive():
                self._record_failure("apple_silicon_telemetry_sampler_join_timeout")
        with self._lock:
            samples = tuple(self._samples)
            failures = tuple(self._failures)
        return _finalize_collection(
            artifact_root=artifact_root,
            run_id=self._run_id,
            samples=samples,
            failures=failures,
            output_token_count=output_token_count,
        )

    def cancel(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.1)

    def _sample_loop(self) -> None:
        for sample_index in range(self._sample_count):
            if self._stop_event.is_set() and sample_index > 0:
                return
            try:
                sample = self._sampler.sample(sample_index=sample_index)
            except AppleSiliconTelemetryError as exc:
                self._record_failure(str(exc))
                return
            with self._lock:
                self._samples.append(sample)
            if sample_index + 1 < self._sample_count:
                self._stop_event.wait(self._sample_interval_s)

    def _record_failure(self, failure: str) -> None:
        if not failure:
            return
        with self._lock:
            self._failures.append(failure)


class MacOSAppleSiliconSampler:
    def __init__(self, *, command_timeout_s: float = 5.0) -> None:
        self._command_timeout_s = command_timeout_s

    def sample(self, *, sample_index: int) -> AppleSiliconTelemetrySample:
        _assert_apple_silicon_macos()
        failures: list[str] = []
        timestamp_unix_ms = int(time.time() * 1000)
        started_at_monotonic_ms = int(time.monotonic() * 1000)
        powermetrics_payload = self._powermetrics_payload(failures)
        memory_used_bytes, memory_total_bytes = self._memory_snapshot(failures)
        processes = self._process_samples(failures)
        return AppleSiliconTelemetrySample(
            timestamp_unix_ms=timestamp_unix_ms,
            sample_index=sample_index,
            started_at_monotonic_ms=started_at_monotonic_ms,
            cpu_utilization_percent=_numeric_probe(powermetrics_payload, ("cpu_average_active_residency", "cpu_utilization_percent", "cpu_active_residency")),
            p_core_utilization_percent=_numeric_probe(powermetrics_payload, ("p_cluster_active_residency", "p_core_utilization_percent", "p_core_active_residency")),
            e_core_utilization_percent=_numeric_probe(powermetrics_payload, ("e_cluster_active_residency", "e_core_utilization_percent", "e_core_active_residency")),
            gpu_utilization_percent=_numeric_probe(powermetrics_payload, ("gpu_active_residency", "gpu_utilization_percent", "gpu_hw_active_residency")),
            gpu_frequency_mhz=_numeric_probe(powermetrics_payload, ("gpu_frequency_mhz", "gpu_average_frequency", "gpu_hw_active_frequency")),
            cpu_power_w=_power_watts(powermetrics_payload, ("cpu_power", "processor_power", "cpu_power_w")),
            gpu_power_w=_power_watts(powermetrics_payload, ("gpu_power", "gpu_power_w")),
            ane_power_w=_power_watts(powermetrics_payload, ("ane_power", "neural_engine_power", "ane_power_w")),
            dram_power_w=_power_watts(powermetrics_payload, ("dram_power", "memory_power", "dram_power_w")),
            system_power_w=_power_watts(powermetrics_payload, ("system_power", "combined_power", "package_power", "system_power_w")),
            memory_used_bytes=memory_used_bytes,
            memory_total_bytes=memory_total_bytes,
            thermal_state=_text_probe(powermetrics_payload, ("thermal_pressure", "thermal_state")),
            processes=processes,
            failures=tuple(failures),
        )

    def _powermetrics_payload(self, failures: list[str]) -> object:
        try:
            completed = subprocess.run(
                [
                    "/usr/bin/powermetrics",
                    "--samplers",
                    "cpu_power,gpu_power,thermal",
                    "--show-process-energy",
                    "-n",
                    "1",
                    "-i",
                    "250",
                    "-f",
                    "plist",
                ],
                capture_output=True,
                timeout=self._command_timeout_s,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            failures.append(f"powermetrics_unavailable:{type(exc).__name__}")
            return {}
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            failures.append(f"powermetrics_failed:{stderr[:160] or completed.returncode}")
            return {}
        try:
            return plistlib.loads(completed.stdout)
        except (plistlib.InvalidFileException, ValueError) as exc:
            failures.append(f"powermetrics_plist_parse_failed:{type(exc).__name__}")
            return {}

    def _memory_snapshot(self, failures: list[str]) -> tuple[int | None, int | None]:
        total = _sysctl_int("hw.memsize", timeout_s=self._command_timeout_s)
        try:
            completed = subprocess.run(
                ["/usr/bin/vm_stat"],
                capture_output=True,
                text=True,
                timeout=self._command_timeout_s,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            failures.append(f"vm_stat_unavailable:{type(exc).__name__}")
            return None, total
        if completed.returncode != 0:
            failures.append(f"vm_stat_failed:{completed.stderr.strip()[:160] or completed.returncode}")
            return None, total
        used = _parse_vm_stat_used_bytes(completed.stdout)
        return used, total

    def _process_samples(self, failures: list[str]) -> tuple[AppleSiliconProcessSample, ...]:
        try:
            completed = subprocess.run(
                ["/bin/ps", "-Ao", "pid=,ppid=,pcpu=,rss=,comm="],
                capture_output=True,
                text=True,
                timeout=self._command_timeout_s,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            failures.append(f"ps_unavailable:{type(exc).__name__}")
            return ()
        if completed.returncode != 0:
            failures.append(f"ps_failed:{completed.stderr.strip()[:160] or completed.returncode}")
            return ()
        return tuple(_parse_process_samples(completed.stdout))


def summarize_samples(
    *,
    time_series_path: str,
    samples: Sequence[AppleSiliconTelemetrySample],
    failures: Sequence[str] = (),
    output_token_count: int = 0,
) -> RunEvidenceTelemetrySummary:
    sample_failures = tuple(
        failure
        for sample in samples
        for failure in sample.failures
    )
    telemetry_failures = tuple(dict.fromkeys((*failures, *sample_failures)))
    if samples and telemetry_failures:
        collector_status = "partial"
    elif samples:
        collector_status = "collected"
    else:
        collector_status = "failed"
    averages = {
        f"average_{key}": _average(getattr(sample, key) for sample in samples)
        for key in _NUMERIC_SAMPLE_KEYS
    }
    peaks = {
        f"peak_{key}": _peak(getattr(sample, key) for sample in samples)
        for key in _NUMERIC_SAMPLE_KEYS
    }
    summary_kwargs: dict[str, object] = {
        "collector_status": collector_status,
        "telemetry_failures": telemetry_failures,
        "time_series_path": time_series_path,
        "sample_count": len(samples),
        "process_attribution": summarize_process_attribution(samples),
        "thermal_events": tuple(
            dict.fromkeys(sample.thermal_state for sample in samples if sample.thermal_state)
        ),
    }
    summary_kwargs.update({key: value for key, value in averages.items() if value is not None})
    summary_kwargs.update({key: value for key, value in peaks.items() if value is not None})
    latest_memory_used = _latest_int(sample.memory_used_bytes for sample in samples)
    latest_memory_total = _latest_int(sample.memory_total_bytes for sample in samples)
    peak_process_memory = _peak_process_memory(samples)
    avg_process_cpu = _average_process_cpu(samples)
    if latest_memory_used is not None:
        summary_kwargs["memory_used_bytes"] = latest_memory_used
    if latest_memory_total is not None:
        summary_kwargs["memory_total_bytes"] = latest_memory_total
    if peak_process_memory is not None:
        summary_kwargs["peak_process_memory_bytes"] = peak_process_memory
    if avg_process_cpu is not None:
        summary_kwargs["average_process_cpu_percent"] = avg_process_cpu
    average_system_power_w = summary_kwargs.get("average_system_power_w")
    if output_token_count > 0 and isinstance(average_system_power_w, float):
        summary_kwargs["watts_per_output_token"] = round(average_system_power_w / output_token_count, 8)
    return RunEvidenceTelemetrySummary(**summary_kwargs)


def summarize_process_attribution(
    samples: Sequence[AppleSiliconTelemetrySample],
) -> dict[str, object]:
    by_process: dict[tuple[int, str, str], dict[str, object]] = {}
    for sample in samples:
        for process in sample.processes:
            key = (process.pid, process.name, process.role)
            row = by_process.setdefault(
                key,
                {
                    "pid": process.pid,
                    "name": process.name,
                    "role": process.role,
                    "port": process.port,
                    "bundle_prefix": process.bundle_prefix,
                    "peak_memory_bytes": 0,
                    "cpu_total": 0.0,
                    "cpu_count": 0,
                    "sample_count": 0,
                },
            )
            if process.memory_bytes is not None:
                row["peak_memory_bytes"] = max(int(row["peak_memory_bytes"]), process.memory_bytes)
            if process.cpu_percent is not None:
                row["cpu_total"] = float(row["cpu_total"]) + process.cpu_percent
                row["cpu_count"] = int(row["cpu_count"]) + 1
            row["sample_count"] = int(row["sample_count"]) + 1
    rows = [_finalize_process_row(row) for row in by_process.values()]
    rows_by_role: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: int(item.get("peak_memory_bytes", 0)), reverse=True):
        rows_by_role[str(row.get("role", ""))].append(row)
    return {
        "primary_runtime_process": _first_or_empty(rows_by_role.get("primary_runtime", [])),
        "control_plane_process": _first_or_empty(rows_by_role.get("control_plane", [])),
        "worker_processes": rows_by_role.get("worker", [])[:8],
        "external_provider_processes": rows_by_role.get("external_provider", [])[:8],
        "process_tree_summary": {
            "sample_count": len(samples),
            "process_count": len(rows),
            "roles": sorted(role for role, role_rows in rows_by_role.items() if role_rows),
        },
    }


def telemetry_probes_for_summary(
    *,
    run_id: str,
    summary: RunEvidenceTelemetrySummary,
    samples: Sequence[AppleSiliconTelemetrySample],
) -> tuple[RunEvidenceProbe, ...]:
    status = "completed" if summary.collector_status == "collected" else "failed"
    error_code = ",".join(summary.telemetry_failures[:2]) if status == "failed" else ""
    started_at = samples[0].started_at_monotonic_ms if samples else int(time.monotonic() * 1000)
    duration_ms = _sample_span_ms(samples)
    attributes = {
        "collector_status": summary.collector_status,
        "sample_count": len(samples),
        "time_series_path": summary.time_series_path,
    }
    return (
        _telemetry_probe(
            run_id=run_id,
            phase="hardware_sample",
            started_at_monotonic_ms=started_at,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            attributes={**attributes, "metrics": _present_hardware_metrics(summary.to_dict())},
        ),
        _telemetry_probe(
            run_id=run_id,
            phase="process_sample",
            started_at_monotonic_ms=started_at,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            attributes=attributes,
        ),
        _telemetry_probe(
            run_id=run_id,
            phase="power_sample",
            started_at_monotonic_ms=started_at,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            attributes=attributes,
        ),
    )


def _finalize_collection(
    *,
    artifact_root: Path,
    run_id: str,
    samples: tuple[AppleSiliconTelemetrySample, ...],
    failures: tuple[str, ...],
    output_token_count: int,
) -> AppleSiliconTelemetryCollection:
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_root / "telemetry-samples.jsonl"
    _write_samples_jsonl(artifact_path, samples=samples, failures=failures)
    summary = summarize_samples(
        time_series_path=artifact_path.name,
        samples=samples,
        failures=failures,
        output_token_count=output_token_count,
    )
    probes = telemetry_probes_for_summary(run_id=run_id, summary=summary, samples=samples)
    return AppleSiliconTelemetryCollection(
        summary=summary,
        samples=samples,
        probes=probes,
        artifact_path=artifact_path,
    )


def _write_samples_jsonl(
    path: Path,
    *,
    samples: Sequence[AppleSiliconTelemetrySample],
    failures: Sequence[str],
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.to_dict(), sort_keys=True) + "\n")
        if failures and not samples:
            handle.write(
                json.dumps(
                    {
                        "schema_version": APPLE_SILICON_TELEMETRY_SAMPLE_SCHEMA_VERSION,
                        "timestamp_unix_ms": int(time.time() * 1000),
                        "sample_kind": "telemetry_failure",
                        "telemetry_failures": list(failures),
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def _telemetry_probe(
    *,
    run_id: str,
    phase: str,
    started_at_monotonic_ms: int,
    duration_ms: float,
    status: str,
    error_code: str,
    attributes: dict[str, object],
) -> RunEvidenceProbe:
    return RunEvidenceProbe(
        run_id=run_id,
        trace_id=f"{run_id}:trace",
        span_id=f"{run_id}:{phase}:{started_at_monotonic_ms}",
        parent_span_id=f"{run_id}:worker_dispatch",
        component="telemetry",
        phase=phase,
        started_at_monotonic_ms=started_at_monotonic_ms,
        duration_ms=max(duration_ms, 0.001),
        status=status,
        error_stage=phase if status == "failed" else "",
        error_code=error_code,
        attributes={key: value for key, value in attributes.items() if value not in ("", None, [])},
    )


def _assert_apple_silicon_macos() -> None:
    if platform.system() != "Darwin" or platform.machine() not in {"arm64", "aarch64"}:
        raise AppleSiliconTelemetryUnsupportedError("unsupported_platform:apple_silicon_macos_required")


def _sysctl_int(name: str, *, timeout_s: float) -> int | None:
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", name],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return int(completed.stdout.strip())
    except ValueError:
        return None


def _parse_vm_stat_used_bytes(output: str) -> int | None:
    page_size = 4096
    pages: dict[str, int] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip().rstrip(".")
        if "page size of" in line:
            for part in line.split():
                if part.isdigit():
                    page_size = int(part)
                    break
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        digits = "".join(character for character in value if character.isdigit())
        if digits:
            pages[key.strip().lower()] = int(digits)
    used_pages = sum(
        pages.get(key, 0)
        for key in (
            "pages active",
            "pages inactive",
            "pages speculative",
            "pages wired down",
            "pages occupied by compressor",
        )
    )
    return used_pages * page_size if used_pages else None


def _parse_process_samples(output: str) -> Iterable[AppleSiliconProcessSample]:
    current_pid = os.getpid()
    for raw_line in output.splitlines():
        parts = raw_line.strip().split(maxsplit=4)
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[0])
            cpu_percent = float(parts[2])
            memory_bytes = int(parts[3]) * 1024
        except ValueError:
            continue
        name = parts[4]
        role = _process_role(name=name, pid=pid, current_pid=current_pid)
        if role == "other":
            continue
        yield AppleSiliconProcessSample(
            pid=pid,
            name=Path(name).name,
            role=role,
            bundle_prefix=_bundle_prefix(name),
            memory_bytes=memory_bytes,
            cpu_percent=cpu_percent,
        )


def _process_role(*, name: str, pid: int, current_pid: int) -> str:
    lowered = name.lower()
    if pid == current_pid or "mlx-worker" in lowered or "melix-mlx-worker" in lowered:
        return "worker"
    if "melixcontrolplane" in lowered or "control-plane" in lowered or "control_plane" in lowered:
        return "control_plane"
    if "ollama" in lowered or "llama" in lowered or "mlx" in lowered or "runtime" in lowered:
        return "primary_runtime"
    if "openai" in lowered or "anthropic" in lowered or "provider" in lowered:
        return "external_provider"
    return "other"


def _bundle_prefix(command: str) -> str:
    parts = Path(command).parts
    if "Applications" in parts:
        index = parts.index("Applications")
        return str(Path(*parts[: index + 2]))
    return ""


def _numeric_probe(payload: object, candidates: Sequence[str]) -> float | None:
    value = _find_value(payload, candidates)
    return _float_or_none(value)


def _power_watts(payload: object, candidates: Sequence[str]) -> float | None:
    value = _float_or_none(_find_value(payload, candidates))
    if value is None:
        return None
    return round(value / 1000.0, 6) if value > 100.0 else round(value, 6)


def _text_probe(payload: object, candidates: Sequence[str]) -> str:
    value = _find_value(payload, candidates)
    return str(value).strip() if value is not None else ""


def _find_value(payload: object, candidates: Sequence[str]) -> object | None:
    normalized_candidates = tuple(_normalize_key(candidate) for candidate in candidates)
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = _normalize_key(str(key))
            if normalized_key in normalized_candidates:
                return value
        for value in payload.values():
            found = _find_value(value, candidates)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_value(item, candidates)
            if found is not None:
                return found
    return None


def _normalize_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _average(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 6) if present else None


def _peak(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(max(present), 6) if present else None


def _latest_int(values: Iterable[int | None]) -> int | None:
    latest: int | None = None
    for value in values:
        if value is not None:
            latest = int(value)
    return latest


def _peak_process_memory(samples: Sequence[AppleSiliconTelemetrySample]) -> int | None:
    values = [
        process.memory_bytes
        for sample in samples
        for process in sample.processes
        if process.memory_bytes is not None
    ]
    return max(values) if values else None


def _average_process_cpu(samples: Sequence[AppleSiliconTelemetrySample]) -> float | None:
    values = [
        process.cpu_percent
        for sample in samples
        for process in sample.processes
        if process.cpu_percent is not None
    ]
    return round(sum(values) / len(values), 6) if values else None


def _sample_span_ms(samples: Sequence[AppleSiliconTelemetrySample]) -> float:
    if not samples:
        return 0.001
    started = samples[0].started_at_monotonic_ms
    ended = samples[-1].started_at_monotonic_ms
    return max(float(ended - started), 0.001)


def _finalize_process_row(row: dict[str, object]) -> dict[str, object]:
    cpu_count = int(row.pop("cpu_count"))
    cpu_total = float(row.pop("cpu_total"))
    row["avg_cpu_percent"] = round(cpu_total / cpu_count, 6) if cpu_count else 0.0
    return row


def _first_or_empty(rows: list[dict[str, object]]) -> dict[str, object]:
    return rows[0] if rows else {}


def _present_hardware_metrics(payload: dict[str, object]) -> list[str]:
    return [
        key
        for key in sorted(payload)
        if key.startswith(("average_", "peak_")) and key.endswith(
            (
                "_utilization_percent",
                "_frequency_mhz",
                "_power_w",
            )
        )
    ]


_NUMERIC_SAMPLE_KEYS = (
    "cpu_utilization_percent",
    "p_core_utilization_percent",
    "e_core_utilization_percent",
    "gpu_utilization_percent",
    "gpu_frequency_mhz",
    "cpu_power_w",
    "gpu_power_w",
    "ane_power_w",
    "dram_power_w",
    "system_power_w",
)
