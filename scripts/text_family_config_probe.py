from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

repo_root = Path.cwd()
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from worker.runtime.text_family_adapters import resolve_text_family_config


class CopyCountingConfig(Mapping[str, Any]):
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)
        self.copy_attempts = 0

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    def keys(self):  # type: ignore[override]
        self.copy_attempts += 1
        return self._payload.keys()


def _payload() -> dict[str, Any]:
    payload: dict[str, Any] = {f"unused_{index}": index for index in range(2048)}
    payload.update(
        {
            "model_type": "qwen3_moe",
            "architectures": ["Qwen3MoeForCausalLM"],
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "rope_interleaved": True,
            "num_local_experts": 128,
            "moe_gate_dequant": True,
        }
    )
    return payload


def _run_sample(*, iterations: int) -> tuple[float, int, int]:
    config = CopyCountingConfig(_payload())
    metadata = {"text_family_id": "qwen3moe"}
    checksum = 0
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(iterations):
        resolved = resolve_text_family_config(
            metadata,
            model_path="models/qwen3-moe-128e",
            config_payload=config,
            default_route_kind="swift_text",
        )
        checksum += resolved.expert_count
        if resolved.rope_profile == "yarn_interleaved":
            checksum += 1
        if resolved.moe_gate_dequant:
            checksum += 1
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if checksum != iterations * 130:
        raise AssertionError(f"unexpected checksum: {checksum}")
    return elapsed_ms, peak_bytes, config.copy_attempts


def main() -> None:
    iterations = 10_000
    elapsed: list[float] = []
    peak: list[int] = []
    copy_calls: list[int] = []
    for _ in range(5):
        elapsed_ms, peak_bytes, copies = _run_sample(iterations=iterations)
        elapsed.append(elapsed_ms)
        peak.append(peak_bytes)
        copy_calls.append(copies)
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed),
                "peak_bytes_mean": statistics.fmean(peak),
                "config_copy_calls_mean": statistics.fmean(copy_calls),
                "iterations": iterations,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
