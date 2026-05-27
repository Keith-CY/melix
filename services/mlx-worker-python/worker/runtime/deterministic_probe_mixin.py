from __future__ import annotations

from typing import Generic, TypeVar

ProbeT = TypeVar("ProbeT")


class DeterministicProbeMixin(Generic[ProbeT]):
    """Mixin that tracks and exposes the last probe snapshot for deterministic runtimes."""

    _last_probe: ProbeT

    def last_probe_snapshot(self) -> ProbeT:
        return self._last_probe
