from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


MELIX_PROBE_MODE_ENV = "MELIX_PROBE_MODE"


class ProbeMode(StrEnum):
    OFF = "off"
    MINIMAL = "minimal"
    SAMPLED = "sampled"
    EVIDENCE = "evidence"
    DEBUG = "debug"


@dataclass(frozen=True)
class ProbePolicy:
    mode: ProbeMode = ProbeMode.MINIMAL
    source_value: str = ""
    fallback_applied: bool = False

    @property
    def telemetry_enabled(self) -> bool:
        return self.mode in {
            ProbeMode.SAMPLED,
            ProbeMode.EVIDENCE,
            ProbeMode.DEBUG,
        }

    @property
    def evidence_enabled(self) -> bool:
        return self.mode in {
            ProbeMode.EVIDENCE,
            ProbeMode.DEBUG,
        }

    @property
    def no_op_reason(self) -> str:
        if self.telemetry_enabled:
            return ""
        return f"probe_mode_{self.mode.value}"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        default_mode: ProbeMode = ProbeMode.MINIMAL,
    ) -> ProbePolicy:
        values = os.environ if env is None else env
        raw_value = values.get(MELIX_PROBE_MODE_ENV, "")
        return cls.from_value(raw_value, default_mode=default_mode)

    @classmethod
    def from_value(
        cls,
        value: str | ProbeMode | None,
        *,
        default_mode: ProbeMode = ProbeMode.MINIMAL,
    ) -> ProbePolicy:
        if isinstance(value, ProbeMode):
            return cls(mode=value, source_value=value.value)
        raw_value = str(value or "").strip().lower()
        if not raw_value:
            return cls(mode=default_mode)
        try:
            return cls(mode=ProbeMode(raw_value), source_value=raw_value)
        except ValueError:
            return cls(
                mode=default_mode,
                source_value=raw_value,
                fallback_applied=True,
            )

    @classmethod
    def evidence(cls) -> ProbePolicy:
        return cls(mode=ProbeMode.EVIDENCE, source_value=ProbeMode.EVIDENCE.value)

    @classmethod
    def debug(cls) -> ProbePolicy:
        return cls(mode=ProbeMode.DEBUG, source_value=ProbeMode.DEBUG.value)


def probe_policy_from_env(env: Mapping[str, str] | None = None) -> ProbePolicy:
    return ProbePolicy.from_env(env)
