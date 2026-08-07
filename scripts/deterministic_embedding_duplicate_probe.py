from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Sequence
from pathlib import Path
from typing import overload

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


class SliceCountingInputs(Sequence[str]):
    def __init__(self, values: list[str]) -> None:
        self._values = values
        self.slice_count = 0

    def __len__(self) -> int:
        return len(self._values)

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> list[str]: ...

    def __getitem__(self, index: int | slice) -> str | list[str]:
        if isinstance(index, slice):
            self.slice_count += 1  # pragma: no cover - regression-only branch
        return self._values[index]


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


def _measure_inputs(
    inputs: Sequence[str],
    *,
    dimensions: int,
    sample_count: int,
) -> tuple[float, float, float, float]:
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
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak_bytes))
        call_samples.append(float(backend.calls))
        checksum = sum(vector[0] for vector in vectors)

    if len(vectors) != len(inputs):
        raise AssertionError(f"unexpected vector count: {len(vectors)} != {len(inputs)}")
    return (
        statistics.fmean(elapsed_samples),
        statistics.fmean(peak_samples),
        statistics.fmean(call_samples),
        checksum,
    )


def _measure_sequence_cycle_detection(
    inputs: list[str],
    *,
    sample_count: int,
) -> tuple[float, float]:
    elapsed_samples: list[float] = []
    slice_samples: list[float] = []
    expected_cycle_length = len(set(inputs))

    for _ in range(sample_count):
        sequence_inputs = SliceCountingInputs(inputs)
        started = time.perf_counter()
        cycle_length = _repeated_input_cycle_length(sequence_inputs)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        slice_samples.append(float(sequence_inputs.slice_count))
        if cycle_length != expected_cycle_length:
            raise AssertionError(  # pragma: no cover - contract guard
                f"unexpected sequence cycle length: {cycle_length} != {expected_cycle_length}"
            )

    return statistics.fmean(elapsed_samples), statistics.fmean(slice_samples)


def run_probe() -> dict[str, float]:
    assert_cycle_detection_contract()
    dimensions = 32
    unique_inputs = [f"document-{index % 160}-payload-{index % 13}" for index in range(512)]
    inputs = [unique_inputs[index % len(unique_inputs)] for index in range(8192)]
    single_cycle_inputs = ["document-single-cycle-payload"] * len(inputs)
    expected_unique_count = len(set(inputs))
    sample_count = 5

    elapsed_mean, peak_mean, call_mean, checksum = _measure_inputs(
        inputs,
        dimensions=dimensions,
        sample_count=sample_count,
    )
    (
        single_cycle_elapsed_mean,
        single_cycle_peak_mean,
        single_cycle_call_mean,
        single_cycle_checksum,
    ) = _measure_inputs(
        single_cycle_inputs,
        dimensions=dimensions,
        sample_count=sample_count,
    )

    sequence_cycle_elapsed_mean, sequence_cycle_slices_mean = (
        _measure_sequence_cycle_detection(inputs, sample_count=sample_count)
    )

    runtime = DeterministicEmbeddingRuntime(dimensions=dimensions)
    backend = CountingEmbeddingBackend()
    loaded_model = {
        "model_id": "melix-dev-embed-counting",
        "dimensions": dimensions,
        "embedding_backend": backend,
        "embedding_family_adapter": CountingEmbeddingFamilyAdapter(),
    }
    vectors = runtime.embed_inputs(loaded_model, inputs)
    assert vectors[0] is not vectors[len(unique_inputs)]
    single_cycle_vectors = runtime.embed_inputs(loaded_model, single_cycle_inputs)
    assert single_cycle_vectors[0] is not single_cycle_vectors[-1]
    return {
        "elapsed_ms_mean": round(elapsed_mean, 6),
        "peak_bytes_mean": round(peak_mean, 6),
        "embed_text_calls_mean": round(call_mean, 6),
        "single_cycle_elapsed_ms_mean": round(single_cycle_elapsed_mean, 6),
        "single_cycle_peak_bytes_mean": round(single_cycle_peak_mean, 6),
        "single_cycle_embed_text_calls_mean": round(single_cycle_call_mean, 6),
        "input_count": float(len(inputs)),
        "unique_input_count": float(expected_unique_count),
        "checksum": round(checksum, 6),
        "single_cycle_checksum": round(single_cycle_checksum, 6),
        "sequence_cycle_detection_elapsed_ms_mean": round(
            sequence_cycle_elapsed_mean,
            6,
        ),
        "sequence_cycle_detection_slices_mean": round(sequence_cycle_slices_mean, 6),
    }


def main() -> None:
    print(json.dumps(run_probe(), sort_keys=True))


if __name__ == "__main__":
    main()
