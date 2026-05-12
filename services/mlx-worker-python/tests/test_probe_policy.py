from __future__ import annotations

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
