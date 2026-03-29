from __future__ import annotations

import os
import time
from collections.abc import Mapping


def configured_delay_ms(kind: str, environment: Mapping[str, str] | None = None) -> float:
    env = environment or os.environ
    specific_key = f"MELIX_DETERMINISTIC_{kind.upper()}_DELAY_MS"
    shared_key = "MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS"

    for key in (specific_key, shared_key):
        raw = env.get(key, "").strip()
        if not raw:
            continue
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 0.0
    return 0.0


def sleep_if_configured(kind: str, environment: Mapping[str, str] | None = None) -> None:
    delay_ms = configured_delay_ms(kind, environment=environment)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
