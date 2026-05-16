from __future__ import annotations

from worker.productization.probe_policy_overhead import (
    NoOpProbeRecorder,
    measure_no_op_probe_policy_overhead,
)
from worker.productization.probe_policy import ProbeMode, ProbePolicy, probe_policy_from_env


def test_probe_policy_parses_supported_modes() -> None:
    assert ProbePolicy.from_value("off").mode == ProbeMode.OFF
    assert ProbePolicy.from_value("minimal").mode == ProbeMode.MINIMAL
    assert ProbePolicy.from_value("sampled").mode == ProbeMode.SAMPLED
    assert ProbePolicy.from_value("evidence").mode == ProbeMode.EVIDENCE
    assert ProbePolicy.from_value("debug").mode == ProbeMode.DEBUG


def test_probe_policy_invalid_env_falls_back_to_production_default() -> None:
    policy = probe_policy_from_env({"MELIX_PROBE_MODE": "definitely-not-valid"})

    assert policy.mode == ProbeMode.MINIMAL
    assert policy.source_value == "definitely-not-valid"
    assert policy.fallback_applied is True
    assert policy.telemetry_enabled is False


def test_probe_policy_empty_env_uses_production_default() -> None:
    policy = probe_policy_from_env({"MELIX_PROBE_MODE": ""})

    assert policy.mode == ProbeMode.MINIMAL
    assert policy.source_value == ""
    assert policy.fallback_applied is False
    assert policy.telemetry_enabled is False


def test_probe_policy_telemetry_enabled_only_for_sampling_modes() -> None:
    assert ProbePolicy(mode=ProbeMode.OFF).telemetry_enabled is False
    assert ProbePolicy(mode=ProbeMode.MINIMAL).telemetry_enabled is False
    assert ProbePolicy(mode=ProbeMode.SAMPLED).telemetry_enabled is True
    assert ProbePolicy(mode=ProbeMode.EVIDENCE).telemetry_enabled is True
    assert ProbePolicy(mode=ProbeMode.DEBUG).telemetry_enabled is True


def test_probe_policy_evidence_enabled_only_for_evidence_modes() -> None:
    assert ProbePolicy(mode=ProbeMode.OFF).evidence_enabled is False
    assert ProbePolicy(mode=ProbeMode.MINIMAL).evidence_enabled is False
    assert ProbePolicy(mode=ProbeMode.SAMPLED).evidence_enabled is False
    assert ProbePolicy(mode=ProbeMode.EVIDENCE).evidence_enabled is True
    assert ProbePolicy(mode=ProbeMode.DEBUG).evidence_enabled is True


def test_probe_policy_uses_slots_for_hot_path_instances() -> None:
    policy = ProbePolicy(mode=ProbeMode.MINIMAL)

    assert not hasattr(policy, "__dict__")
    assert policy.telemetry_enabled is False
    assert policy.no_op_reason == "probe_mode_minimal"
    assert ProbePolicy(mode=ProbeMode.EVIDENCE).no_op_reason == ""


def test_no_op_probe_recorder_and_metrics_use_slots_for_hot_path() -> None:
    recorder = NoOpProbeRecorder()
    metrics = measure_no_op_probe_policy_overhead(iterations=1, samples=1)

    assert not hasattr(recorder, "__dict__")
    assert not hasattr(metrics, "__dict__")
    assert recorder.record() is None


def test_no_op_probe_policy_overhead_metrics_are_thresholded() -> None:
    metrics = measure_no_op_probe_policy_overhead(iterations=16, samples=1, threshold_pct=10_000.0)
    payload = metrics.to_dict()

    assert payload["iteration_count"] == 16.0
    assert payload["sample_count"] == 1.0
    assert payload["no_op_recorder_call_ms_mean"] >= 0.0
    assert payload["no_op_policy_check_call_ms_mean"] >= 0.0
    assert payload["no_op_reason_call_ms_mean"] >= 0.0
    assert "no_op_recorder_delta_ms" in payload
    assert "no_op_policy_check_delta_ms" in payload
    assert "no_op_reason_delta_ms" in payload
    assert payload["absolute_tolerance_ms"] > 0.0
    assert payload["threshold_passed"] == 1.0
