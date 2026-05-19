from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops import training_config  # noqa: E402

SAMPLES = int(os.environ.get("MELIX_TRAINING_CONFIG_TARGET_MODULE_SAMPLES", "7"))
ITERATIONS = int(os.environ.get("MELIX_TRAINING_CONFIG_TARGET_MODULE_ITERATIONS", "50000"))
CASES = (
    ("qwen", "@attention,q_proj,attention"),
    ("qwen3moe", "attention_experts,@experts,q_proj"),
    ("mixtral", ""),
    ("gemma", "@gated_mlp,gate_proj"),
)
EXPECTED = {
    ("qwen", "@attention,q_proj,attention"): ("q_proj", "k_proj", "v_proj", "o_proj"),
    ("qwen3moe", "attention_experts,@experts,q_proj"): (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ),
    ("mixtral", ""): ("q_proj", "k_proj", "v_proj", "o_proj"),
    ("gemma", "@gated_mlp,gate_proj"): ("gate_proj", "up_proj", "down_proj"),
}


def _prewarm_cache() -> None:
    for family_id, raw_value in CASES:
        training_config._resolve_target_modules(
            raw_value,
            profile=training_config._FAMILY_PROFILES[family_id],
        )


def _run_once() -> tuple[float, float, int]:
    checksum = 0
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(ITERATIONS):
        for family_id, raw_value in CASES:
            resolved = training_config._resolve_target_modules(
                raw_value,
                profile=training_config._FAMILY_PROFILES[family_id],
            )
            if tuple(resolved) != EXPECTED[(family_id, raw_value)]:
                raise AssertionError(f"unexpected targets for {family_id}: {resolved!r}")
            checksum += len(resolved)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed_ms, float(peak_bytes), checksum


def main() -> None:
    _prewarm_cache()
    samples = [_run_once() for _ in range(SAMPLES)]
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(sample[0] for sample in samples),
                "peak_bytes_mean": statistics.fmean(sample[1] for sample in samples),
                "checksum": float(samples[-1][2]),
                "iteration_count": float(ITERATIONS),
                "case_count": float(len(CASES)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
