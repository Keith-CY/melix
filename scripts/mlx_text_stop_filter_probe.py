from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

_SCRIPT_PATH = globals().get("__file__")
REPO_ROOT = Path(_SCRIPT_PATH).resolve().parents[1] if _SCRIPT_PATH else Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import mlx_text_runtime as mlx_text_runtime_module
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent


def _measure(sample_count: int | None = None, token_event_count: int | None = None) -> dict[str, float]:
    runtime = MLXTextRuntime(backend=object())
    stop_sequences = ("<stop>", "</turn>", "END_OF_MESSAGE", "[[done]]", "###")
    if sample_count is None:
        sample_count = int(os.environ.get("MELIX_MLX_TEXT_STOP_FILTER_SAMPLES", "5"))
    if token_event_count is None:
        token_event_count = int(os.environ.get("MELIX_MLX_TEXT_STOP_FILTER_EVENTS", "60000"))
    chunks = tuple(RuntimeTokenEvent(text="token ", prompt_tokens=1, completion_tokens=index) for index in range(token_event_count))
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    prefix_length_computations: list[float] = []

    for _ in range(sample_count):
        computation_count = 0
        restore = None
        if hasattr(mlx_text_runtime_module, "_stop_sequence_max_prefix_length"):
            original = mlx_text_runtime_module._stop_sequence_max_prefix_length

            def counted_max_prefix_length(sequences: tuple[str, ...]) -> int:
                nonlocal computation_count
                computation_count += 1
                return original(sequences)

            restore = ("_stop_sequence_max_prefix_length", original)
            mlx_text_runtime_module._stop_sequence_max_prefix_length = counted_max_prefix_length
        else:
            original = mlx_text_runtime_module._viable_stop_prefix_suffix

            def counted_viable_suffix(text: str, sequences: tuple[str, ...]) -> str:
                nonlocal computation_count
                computation_count += 1
                return original(text, sequences)

            restore = ("_viable_stop_prefix_suffix", original)
            mlx_text_runtime_module._viable_stop_prefix_suffix = counted_viable_suffix

        tracemalloc.start()
        start = time.perf_counter()
        emitted = list(runtime._apply_stop_sequences(chunks, stop_sequences))
        elapsed_ms.append((time.perf_counter() - start) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        peak_bytes.append(float(peak))
        tracemalloc.stop()
        setattr(mlx_text_runtime_module, restore[0], restore[1])

        if len(emitted) != token_event_count:
            raise RuntimeError(f"unexpected emitted count: {len(emitted)}")
        if "".join(event.text for event in emitted) != "token " * token_event_count:
            raise RuntimeError("stop filter changed visible text")
        prefix_length_computations.append(float(computation_count))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "prefix_length_computations_mean": statistics.fmean(prefix_length_computations),
        "token_event_count": float(token_event_count),
        "stop_sequence_count": float(len(stop_sequences)),
    }


if __name__ == "__main__":
    print(json.dumps(_measure(), sort_keys=True))
