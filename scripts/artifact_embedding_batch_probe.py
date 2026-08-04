from __future__ import annotations

import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any


REPO_ROOT = Path(os.environ.get("MELIX_ARTIFACT_EMBEDDING_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

try:
    from worker.runtime.artifact_embedding_runtime import (
        ArtifactEmbeddingDescriptor,
        MLXArtifactEmbeddingBackend,
        MLXEmbeddingRuntime,
    )
except ImportError:  # pragma: no cover - base revision compatibility
    ArtifactEmbeddingDescriptor = None  # type: ignore[assignment,misc]
    MLXArtifactEmbeddingBackend = None  # type: ignore[assignment,misc]
    MLXEmbeddingRuntime = None  # type: ignore[assignment,misc]


_BATCH_SIZE = 32
_DIMENSIONS = 16


class ProbeTokenizer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, inputs: Any, **_kwargs: Any) -> dict[str, list[list[int]]]:
        self.calls += 1
        return {
            "input_ids": [
                [101, 1000 + (index % 97), 102, 0]
                for index, _input in enumerate(inputs)
            ],
            "attention_mask": [[1, 1, 1, 0] for _input in inputs],
            "token_type_ids": [[0, 0, 0, 0] for _input in inputs],
        }


class ProbeEncoder:
    def __init__(self, *, work_units: int) -> None:
        self.work_units = work_units
        self.calls = 0

    def __call__(self, **kwargs: Any) -> Any:
        import mlx.core as mx

        self.calls += 1
        accumulator = 0.0
        for index in range(self.work_units):
            accumulator += math.sin(index * 0.0001)
        input_ids = kwargs["input_ids"]
        batch_size, sequence_length = input_ids.shape
        seed = mx.array(accumulator * 1e-12, dtype=mx.float32)
        values = mx.arange(
            batch_size * sequence_length * _DIMENSIONS,
            dtype=mx.float32,
        ).reshape(batch_size, sequence_length, _DIMENSIONS)
        return values * mx.array(1e-4, dtype=mx.float32) + seed


def _probe_backend(*, work_units: int) -> tuple[Any, ProbeTokenizer, ProbeEncoder]:
    tokenizer = ProbeTokenizer()
    encoder = ProbeEncoder(work_units=work_units)
    assert MLXArtifactEmbeddingBackend is not None
    return (
        MLXArtifactEmbeddingBackend(
            tokenizer=tokenizer,
            encoder=encoder,
            dtype="float32",
        ),
        tokenizer,
        encoder,
    )


def _descriptor() -> Any:
    return ArtifactEmbeddingDescriptor(
        model_path=REPO_ROOT,
        architecture="bert",
        backend_id="mlx-bert-v1",
        config={},
        config_path=REPO_ROOT / "config.json",
        tokenizer_paths=(),
        weight_paths=(),
        model_hash="sha256:probe",
        tokenizer_hash="sha256:probe",
        pooling_mode="mean",
        normalization="l2",
        dimensions=_DIMENSIONS,
        max_length=32,
        vector_kind="single_dense",
        dtype="float32",
        estimated_resident_bytes=0,
    )


def _loaded_model(backend: Any) -> dict[str, object]:
    return {
        "model_id": "artifact-embedding-probe",
        "dimensions": _DIMENSIONS,
        "embedding_backend_id": "mlx-bert-v1",
        "embedding_backend": backend,
        "embedding_artifact_descriptor": _descriptor(),
    }


def _output_errors(vectors: list[list[float]]) -> tuple[int, int]:
    nonfinite = sum(
        1 for vector in vectors for value in vector if not math.isfinite(value)
    )
    dimension_mismatches = sum(1 for vector in vectors if len(vector) != _DIMENSIONS)
    return nonfinite, dimension_mismatches


def _legacy_embed(input_text: str, *, work_units: int) -> list[float]:
    accumulator = 0.0
    for index in range(work_units):
        accumulator += math.sin(index * 0.0001)
    seed = accumulator * 1e-12 + len(input_text) * 1e-6
    return [seed + dimension / 17.0 for dimension in range(_DIMENSIONS)]


def measure(*, sample_count: int, work_units: int) -> dict[str, float]:
    inputs = tuple(f"document-{index}" for index in range(_BATCH_SIZE))
    batch_elapsed: list[float] = []
    singleton_elapsed: list[float] = []
    batch_forward_counts: list[float] = []
    singleton_forward_counts: list[float] = []
    batch_tokenizer_counts: list[float] = []
    singleton_tokenizer_counts: list[float] = []
    nonfinite_output_count = 0
    output_dimension_mismatch_count = 0
    checksum = 0.0

    if MLXEmbeddingRuntime is not None and MLXArtifactEmbeddingBackend is not None:
        warm_backend, _warm_tokenizer, _warm_encoder = _probe_backend(work_units=1)
        MLXEmbeddingRuntime().embed_inputs(
            _loaded_model(warm_backend),
            ("warmup",),
        )

    for _ in range(sample_count):
        started = time.perf_counter()
        if MLXEmbeddingRuntime is None or MLXArtifactEmbeddingBackend is None:
            batch_vectors = [
                _legacy_embed(input_text, work_units=work_units)
                for input_text in inputs
            ]
            batch_forward_count = float(_BATCH_SIZE)
            batch_tokenizer_count = float(_BATCH_SIZE)
        else:
            batch_backend, batch_tokenizer, batch_encoder = _probe_backend(
                work_units=work_units
            )
            runtime = MLXEmbeddingRuntime(backend_loader=lambda descriptor: object())
            batch_vectors = runtime.embed_inputs(_loaded_model(batch_backend), inputs)
            batch_forward_count = float(batch_encoder.calls)
            batch_tokenizer_count = float(batch_tokenizer.calls)
        batch_elapsed.append(time.perf_counter() - started)
        batch_forward_counts.append(batch_forward_count)
        batch_tokenizer_counts.append(batch_tokenizer_count)

        singleton_vectors: list[list[float]] = []
        started = time.perf_counter()
        if MLXEmbeddingRuntime is None or MLXArtifactEmbeddingBackend is None:
            singleton_vectors = [
                _legacy_embed(input_text, work_units=work_units)
                for input_text in inputs
            ]
            singleton_forward_count = float(_BATCH_SIZE)
            singleton_tokenizer_count = float(_BATCH_SIZE)
        else:
            singleton_backend, singleton_tokenizer, singleton_encoder = _probe_backend(
                work_units=work_units
            )
            singleton_model = _loaded_model(singleton_backend)
            for input_text in inputs:
                singleton_vectors.extend(
                    runtime.embed_inputs(singleton_model, (input_text,))
                )
            singleton_forward_count = float(singleton_encoder.calls)
            singleton_tokenizer_count = float(singleton_tokenizer.calls)
        singleton_elapsed.append(time.perf_counter() - started)
        singleton_forward_counts.append(singleton_forward_count)
        singleton_tokenizer_counts.append(singleton_tokenizer_count)

        for vectors in (batch_vectors, singleton_vectors):
            nonfinite, dimension_mismatches = _output_errors(vectors)
            nonfinite_output_count += nonfinite
            output_dimension_mismatch_count += dimension_mismatches
            checksum += sum(vector[0] for vector in vectors)

    batch_seconds = statistics.fmean(batch_elapsed)
    singleton_seconds = statistics.fmean(singleton_elapsed)
    batch_samples_per_second = _BATCH_SIZE / max(batch_seconds, 1e-12)
    singleton_samples_per_second = _BATCH_SIZE / max(singleton_seconds, 1e-12)
    return {
        "batch_32_forward_count": statistics.fmean(batch_forward_counts),
        "batch_32_tokenizer_count": statistics.fmean(batch_tokenizer_counts),
        "batch_32_samples_per_second": batch_samples_per_second,
        "singleton_32_forward_count": statistics.fmean(singleton_forward_counts),
        "singleton_32_tokenizer_count": statistics.fmean(singleton_tokenizer_counts),
        "singleton_32_samples_per_second": singleton_samples_per_second,
        "batch_speedup_ratio": batch_samples_per_second / max(singleton_samples_per_second, 1e-12),
        "nonfinite_output_count": float(nonfinite_output_count),
        "output_dimension_mismatch_count": float(output_dimension_mismatch_count),
        "sample_count": float(sample_count),
        "work_units": float(work_units),
        "checksum": checksum,
    }


def main() -> int:
    sample_count = int(os.environ.get("MELIX_ARTIFACT_EMBEDDING_SAMPLES", "5"))
    work_units = int(os.environ.get("MELIX_ARTIFACT_EMBEDDING_WORK_UNITS", "20000"))
    print(json.dumps(measure(sample_count=sample_count, work_units=work_units), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
