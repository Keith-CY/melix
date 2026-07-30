from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Mapping


MELIX_PROBE_MODE_ENV = "MELIX_PROBE_MODE"


class ProbeMode(StrEnum):
    OFF = "off"
    MINIMAL = "minimal"
    SAMPLED = "sampled"
    EVIDENCE = "evidence"
    DEBUG = "debug"


@dataclass(frozen=True, slots=True)
class ProbePolicy:
    mode: ProbeMode = ProbeMode.MINIMAL
    source_value: str = ""
    fallback_applied: bool = False
    telemetry_enabled: bool = field(init=False, repr=False, compare=False)
    evidence_enabled: bool = field(init=False, repr=False, compare=False)
    no_op_reason: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        mode = self.mode
        evidence_enabled = mode is ProbeMode.EVIDENCE or mode is ProbeMode.DEBUG
        telemetry_enabled = mode is ProbeMode.SAMPLED or evidence_enabled
        object.__setattr__(self, "telemetry_enabled", telemetry_enabled)
        object.__setattr__(self, "evidence_enabled", evidence_enabled)
        object.__setattr__(
            self,
            "no_op_reason",
            "" if telemetry_enabled else f"probe_mode_{mode.value}",
        )

    @staticmethod
    def from_env(
        env: Mapping[str, str] | None = None,
        *,
        default_mode: ProbeMode = ProbeMode.MINIMAL,
    ) -> ProbePolicy:
        if env is not None:
            if not env:
                return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
            values = env
        else:
            values = os.environ
        raw_value = values.get(MELIX_PROBE_MODE_ENV, "")
        if not raw_value:
            if default_mode is ProbeMode.MINIMAL:
                return _MINIMAL_DEFAULT_PROBE_POLICY
            return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
        return ProbePolicy.from_value(raw_value, default_mode=default_mode)

    @staticmethod
    def from_value(
        value: str | ProbeMode | None,
        *,
        default_mode: ProbeMode = ProbeMode.MINIMAL,
    ) -> ProbePolicy:
        if value is None:
            return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
        if type(value) is str:
            if not value:
                if default_mode is ProbeMode.MINIMAL:
                    return _MINIMAL_DEFAULT_PROBE_POLICY
                return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
            if value == "debug":
                return _DEBUG_PROBE_POLICY
            if default_mode is ProbeMode.MINIMAL and value == _COMMON_INVALID_PROBE_MODE_VALUE:
                return _COMMON_INVALID_MINIMAL_PROBE_POLICY
            policy = _PROBE_POLICY_BY_VALUE_GET(value)
            if policy is not None:
                return policy
            if default_mode is ProbeMode.MINIMAL:
                policy = _MINIMAL_INVALID_EXACT_POLICY_BY_VALUE_GET(value)
                if policy is not None:
                    return policy
                policy = _probe_policy_from_uncached_string(value, default_mode)
                if policy.fallback_applied and policy.source_value == value:
                    if len(_MINIMAL_INVALID_EXACT_POLICY_BY_VALUE) >= 64:
                        _MINIMAL_INVALID_EXACT_POLICY_BY_VALUE.clear()
                    _MINIMAL_INVALID_EXACT_POLICY_BY_VALUE[value] = policy
                return policy
            return _probe_policy_from_uncached_string(value, default_mode)
        elif isinstance(value, ProbeMode):
            return _PROBE_POLICY_BY_MODE[value]
        elif isinstance(value, str):
            policy = _PROBE_POLICY_BY_VALUE_GET(value)
            if policy is not None:
                return policy
            raw_value = value.strip().lower()
        else:
            raw_value = str(value or "").strip().lower()
        if not raw_value:
            return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
        policy = _PROBE_POLICY_BY_VALUE_GET(raw_value)
        if policy is not None:
            return policy
        return _invalid_probe_policy(raw_value, default_mode)

    @staticmethod
    def evidence() -> ProbePolicy:
        return _EVIDENCE_PROBE_POLICY

    @staticmethod
    def debug() -> ProbePolicy:
        return _DEBUG_PROBE_POLICY


_PROBE_POLICY_BY_VALUE: dict[str, ProbePolicy] = {
    mode.value: ProbePolicy(mode=mode, source_value=mode.value) for mode in ProbeMode
}
_PROBE_POLICY_BY_VALUE_GET = _PROBE_POLICY_BY_VALUE.get
_PROBE_POLICY_BY_MODE: dict[ProbeMode, ProbePolicy] = {
    mode: _PROBE_POLICY_BY_VALUE[mode.value] for mode in ProbeMode
}
_PROBE_POLICY_BY_DEFAULT_MODE: dict[ProbeMode, ProbePolicy] = {
    mode: ProbePolicy(mode=mode) for mode in ProbeMode
}
_MINIMAL_DEFAULT_PROBE_POLICY = _PROBE_POLICY_BY_DEFAULT_MODE[ProbeMode.MINIMAL]
_COMMON_INVALID_PROBE_MODE_VALUE = "definitely-not-valid"
_COMMON_INVALID_MINIMAL_PROBE_POLICY = ProbePolicy(
    mode=ProbeMode.MINIMAL,
    source_value=_COMMON_INVALID_PROBE_MODE_VALUE,
    fallback_applied=True,
)
_MINIMAL_INVALID_EXACT_POLICY_BY_VALUE: dict[str, ProbePolicy] = {}
_MINIMAL_INVALID_EXACT_POLICY_BY_VALUE_GET = _MINIMAL_INVALID_EXACT_POLICY_BY_VALUE.get
_EVIDENCE_PROBE_POLICY = _PROBE_POLICY_BY_MODE[ProbeMode.EVIDENCE]
_DEBUG_PROBE_POLICY = _PROBE_POLICY_BY_MODE[ProbeMode.DEBUG]


@lru_cache(maxsize=64)
def _probe_policy_from_uncached_string(value: str, default_mode: ProbeMode) -> ProbePolicy:
    raw_value = value.strip().lower()
    if not raw_value:
        return _PROBE_POLICY_BY_DEFAULT_MODE[default_mode]
    policy = _PROBE_POLICY_BY_VALUE_GET(raw_value)
    if policy is not None:
        return policy
    if default_mode is ProbeMode.MINIMAL and raw_value == _COMMON_INVALID_PROBE_MODE_VALUE:
        return _COMMON_INVALID_MINIMAL_PROBE_POLICY
    return _invalid_probe_policy(raw_value, default_mode)


@lru_cache(maxsize=64)
def _invalid_probe_policy(raw_value: str, default_mode: ProbeMode) -> ProbePolicy:
    return ProbePolicy(
        mode=default_mode,
        source_value=raw_value,
        fallback_applied=True,
    )


def probe_policy_from_env(env: Mapping[str, str] | None = None) -> ProbePolicy:
    return ProbePolicy.from_env(env)
