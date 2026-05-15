from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

from worker.productization.probe_policy import ProbeMode, ProbePolicy


def _no_op_call() -> None:
    return None


class NoOpProbeRecorder:
    record = staticmethod(_no_op_call)


@dataclass(frozen=True)
class ProbeOverheadMetrics:
    sample_count: int
    iteration_count: int
    baseline_call_ms_mean: float
    no_op_recorder_call_ms_mean: float
    no_op_policy_check_call_ms_mean: float
    no_op_reason_call_ms_mean: float
    no_op_recorder_overhead_pct: float
    no_op_policy_check_overhead_pct: float
    no_op_reason_overhead_pct: float
    no_op_recorder_delta_ms: float
    no_op_policy_check_delta_ms: float
    no_op_reason_delta_ms: float
    threshold_pct: float
    absolute_tolerance_ms: float
    threshold_passed: bool

    def to_dict(self) -> dict[str, float]:
        return {
            "sample_count": float(self.sample_count),
            "iteration_count": float(self.iteration_count),
            "baseline_call_ms_mean": self.baseline_call_ms_mean,
            "no_op_recorder_call_ms_mean": self.no_op_recorder_call_ms_mean,
            "no_op_policy_check_call_ms_mean": self.no_op_policy_check_call_ms_mean,
            "no_op_reason_call_ms_mean": self.no_op_reason_call_ms_mean,
            "no_op_recorder_overhead_pct": self.no_op_recorder_overhead_pct,
            "no_op_policy_check_overhead_pct": self.no_op_policy_check_overhead_pct,
            "no_op_reason_overhead_pct": self.no_op_reason_overhead_pct,
            "no_op_recorder_delta_ms": self.no_op_recorder_delta_ms,
            "no_op_policy_check_delta_ms": self.no_op_policy_check_delta_ms,
            "no_op_reason_delta_ms": self.no_op_reason_delta_ms,
            "threshold_pct": self.threshold_pct,
            "absolute_tolerance_ms": self.absolute_tolerance_ms,
            "threshold_passed": 1.0 if self.threshold_passed else 0.0,
        }


def measure_no_op_probe_policy_overhead(
    *,
    iterations: int = 200_000,
    samples: int = 5,
    threshold_pct: float = 5.0,
    absolute_tolerance_ms: float = 0.000_005,
) -> ProbeOverheadMetrics:
    iteration_count = max(int(iterations), 1)
    sample_count = max(int(samples), 1)
    recorder = NoOpProbeRecorder()
    policy = ProbePolicy(mode=ProbeMode.MINIMAL)

    baseline_samples = _sample_call_ms(_no_op_call, iterations=iteration_count, samples=sample_count)
    recorder_samples = _sample_call_ms(
        recorder.record,
        iterations=iteration_count,
        samples=sample_count,
    )
    policy_samples = _sample_call_ms(
        lambda: policy.telemetry_enabled,
        iterations=iteration_count,
        samples=sample_count,
    )
    reason_samples = _sample_call_ms(
        lambda: policy.no_op_reason,
        iterations=iteration_count,
        samples=sample_count,
    )
    baseline_mean = _mean(baseline_samples)
    recorder_mean = _mean(recorder_samples)
    policy_mean = _mean(policy_samples)
    reason_mean = _mean(reason_samples)
    recorder_overhead_pct = _overhead_pct(recorder_mean, baseline_mean)
    policy_overhead_pct = _overhead_pct(policy_mean, baseline_mean)
    reason_overhead_pct = _overhead_pct(reason_mean, baseline_mean)
    recorder_delta_ms = round(recorder_mean - baseline_mean, 9)
    policy_delta_ms = round(policy_mean - baseline_mean, 9)
    reason_delta_ms = round(reason_mean - baseline_mean, 9)
    return ProbeOverheadMetrics(
        sample_count=sample_count,
        iteration_count=iteration_count,
        baseline_call_ms_mean=baseline_mean,
        no_op_recorder_call_ms_mean=recorder_mean,
        no_op_policy_check_call_ms_mean=policy_mean,
        no_op_reason_call_ms_mean=reason_mean,
        no_op_recorder_overhead_pct=recorder_overhead_pct,
        no_op_policy_check_overhead_pct=policy_overhead_pct,
        no_op_reason_overhead_pct=reason_overhead_pct,
        no_op_recorder_delta_ms=recorder_delta_ms,
        no_op_policy_check_delta_ms=policy_delta_ms,
        no_op_reason_delta_ms=reason_delta_ms,
        threshold_pct=float(threshold_pct),
        absolute_tolerance_ms=float(absolute_tolerance_ms),
        threshold_passed=recorder_overhead_pct <= threshold_pct
        or recorder_delta_ms <= absolute_tolerance_ms,
    )


def _sample_call_ms(call: Callable[[], object], *, iterations: int, samples: int) -> list[float]:
    measurements: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        for _ in range(iterations):
            call()
        measurements.append(((time.perf_counter() - started) * 1000.0) / iterations)
    return measurements


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 9)


def _overhead_pct(candidate: float, baseline: float) -> float:
    if baseline <= 0.0:
        return 0.0 if candidate <= 0.0 else 100.0
    return round(((candidate - baseline) / baseline) * 100.0, 6)
