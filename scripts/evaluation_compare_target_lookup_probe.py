from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.evaluation_compare import resolve_compare_target_models


class SyntheticRegistry:
    def __init__(self, model_ids: list[str]) -> None:
        self._handles = [f"handle-{index}" for index in range(len(model_ids))]
        self._loaded_by_handle = {
            handle: SimpleNamespace(spec=SimpleNamespace(model_id=model_id))
            for handle, model_id in zip(self._handles, model_ids, strict=True)
        }
        self.get_loaded_model_call_count = 0

    def list_loaded_models(self) -> list[str]:
        return list(self._handles)

    def get_loaded_model(self, handle: str) -> object | None:
        self.get_loaded_model_call_count += 1
        return self._loaded_by_handle.get(handle)


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    return int(raw_value) if raw_value else default


def main() -> int:
    loaded_count = _int_env("MELIX_EVAL_COMPARE_TARGET_LOOKUP_MODELS", 10000)
    iterations = _int_env("MELIX_EVAL_COMPARE_TARGET_LOOKUP_ITERATIONS", 400)
    samples = _int_env("MELIX_EVAL_COMPARE_TARGET_LOOKUP_SAMPLES", 5)
    target_ids = ("target-a", "target-b", "target-c")
    model_ids = [*target_ids, *[f"unused-{index}" for index in range(loaded_count - len(target_ids))]]

    elapsed_samples: list[float] = []
    calls_per_iteration_samples: list[float] = []
    checksum = 0
    for _ in range(samples):
        registry = SyntheticRegistry(model_ids)
        started = time.perf_counter()
        for _ in range(iterations):
            resolved = resolve_compare_target_models(
                registry=registry,
                target_model_ids=target_ids,
            )
            checksum += len(resolved)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        calls_per_iteration_samples.append(registry.get_loaded_model_call_count / iterations)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "get_loaded_model_calls_mean": round(
                    statistics.fmean(calls_per_iteration_samples), 6
                ),
                "loaded_model_count": float(loaded_count),
                "target_count": float(len(target_ids)),
                "checksum": float(checksum),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    main()
