from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

repo_root = Path.cwd()
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from worker.runtime.deterministic_embedding_runtime import (
    DeterministicEmbeddingRuntime,
    _repeated_input_cycle_length,
)
from worker.runtime.embedding_backends import (
    DeterministicEmbeddingBackend,
    DeterministicEmbeddingFamilyAdapter,
    EmbeddingBackendDescriptor,
    EmbeddingFamilyDescriptor,
)


class CountingEmbeddingBackend(DeterministicEmbeddingBackend):
    descriptor = EmbeddingBackendDescriptor(
        backend_id="counting-v1",
        family_id="counting",
        pooling_mode="mean",
        normalization="none",
        estimated_resident_bytes=1,
    )

    def __init__(self) -> None:
        self.calls = 0

    def embed_text(self, text: str, dimensions: int) -> list[float]:
        self.calls += 1
        seed = (len(text) % 17) / 17.0
        return [seed + (index / 1000.0) for index in range(dimensions)]


class CountingEmbeddingFamilyAdapter(DeterministicEmbeddingFamilyAdapter):
    descriptor = EmbeddingFamilyDescriptor(
        family_id="counting",
        pooling_mode="mean",
        normalization="none",
        default_dimensions=32,
    )

    def embed_text(
        self,
        backend: DeterministicEmbeddingBackend,
        text: str,
        dimensions: int,
    ) -> list[float]:
        return backend.embed_text(text, dimensions)


def assert_cycle_detection_contract() -> None:
    no_repeat = [f"unique-{index}" for index in range(1024)]
    uneven_repeat = (
        ["repeat"]
        + [f"uneven-{index}" for index in range(511)]
        + ["repeat"]
        + [f"tail-{index}" for index in range(512)]
    )
    mismatched_cycle = (
        [f"cycle-{index}" for index in range(512)]
        + ["cycle-0"]
        + [f"mismatch-{index}" for index in range(511)]
    )
    valid_cycle = [f"cycle-{index}" for index in range(512)] * 2

    assert _repeated_input_cycle_length(no_repeat) == 0
    assert _repeated_input_cycle_length(uneven_repeat) == 0
    assert _repeated_input_cycle_length(mismatched_cycle) == 0
    assert _repeated_input_cycle_length(valid_cycle) == 512


def run_probe() -> dict[str, float]:
    assert_cycle_detection_contract()
    dimensions = 32
    unique_inputs = [f"document-{index % 160}-payload-{index % 13}" for index in range(512)]
    inputs = [unique_inputs[index % len(unique_inputs)] for index in range(8192)]
    expected_unique_count = len(set(inputs))
    sample_count = 5
    elapsed_samples: list[float] = []
    call_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0

    for _ in range(sample_count):
        backend = CountingEmbeddingBackend()
        runtime = DeterministicEmbeddingRuntime(dimensions=dimensions)
        loaded_model = {
            "model_id": "melix-dev-embed-counting",
            "dimensions": dimensions,
            "embedding_backend": backend,
            "embedding_family_adapter": CountingEmbeddingFamilyAdapter(),
        }
        tracemalloc.start()
        started = time.perf_counter()
        vectors = runtime.embed_inputs(loaded_model, inputs)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
        call_samples.append(float(backend.calls))
        checksum = sum(vector[0] for vector in vectors)

    if len(vectors) != len(inputs):
        raise AssertionError(f"unexpected vector count: {len(vectors)} != {len(inputs)}")
    assert vectors[0] is not vectors[len(unique_inputs)]
    return {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
        "embed_text_calls_mean": round(statistics.fmean(call_samples), 6),
        "input_count": float(len(inputs)),
        "unique_input_count": float(expected_unique_count),
        "checksum": round(checksum, 6),
    }


def main() -> None:
    print(json.dumps(run_probe(), sort_keys=True))


if __name__ == "__main__":
    main()
