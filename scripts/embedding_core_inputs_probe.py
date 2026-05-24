from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(os.environ.get("MELIX_EMBEDDING_CORE_INPUTS_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2  # noqa: E402
from worker.engine.embedding_core import EmbeddingCore  # noqa: E402
from worker.registry import LoadedModel  # noqa: E402


class ProbeEmbeddingRuntime:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.input_type_names: list[str] = []
        self.input_lengths: list[int] = []

    def embed_inputs(
        self,
        loaded_model: dict[str, object],
        inputs: Sequence[str],
    ) -> list[list[float]]:
        self.input_type_names.append(type(inputs).__name__)
        input_count = len(inputs)
        self.input_lengths.append(input_count)
        dimensions = int(loaded_model.get("dimensions", self.dimensions))
        return [[float((index % 17) + offset) for offset in range(dimensions)] for index in range(input_count)]


class ProbeRegistry:
    def __init__(self, runtime: ProbeEmbeddingRuntime) -> None:
        self.embedding_runtime = runtime
        self.loaded_model = LoadedModel(
            handle="embedding-probe-handle",
            spec=common_pb2.ModelSpec(model_id="embedding-probe-model"),
            runtime_model={"dimensions": runtime.dimensions},
            runtime=runtime,
            estimated_resident_bytes=1,
            runtime_kind="embedding",
            residency=common_pb2.ResidencyInfo(),
            load_trust=common_pb2.ModelLoadTrustPolicy(),
        )

    def get_loaded_model(self, model_handle: str) -> LoadedModel | None:
        if model_handle != self.loaded_model.handle:
            return None
        return self.loaded_model


def _build_request(input_count: int) -> inference_pb2.EmbedRequest:
    request = inference_pb2.EmbedRequest(
        id=common_pb2.RequestIdentity(request_id="embedding-core-inputs-probe"),
        model_handle="embedding-probe-handle",
    )
    request.inputs.extend(f"document-{index % 4096}-payload" for index in range(input_count))
    return request


def measure(iterations: int, sample_count: int, input_count: int, dimensions: int) -> dict[str, float | str]:
    request = _build_request(input_count)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0
    input_type_name = ""

    for _ in range(sample_count):
        runtime = ProbeEmbeddingRuntime(dimensions=dimensions)
        service = EmbeddingCore(ProbeRegistry(runtime))  # type: ignore[arg-type]
        tracemalloc.start()
        started = time.perf_counter()
        for _iteration in range(iterations):
            response = service.embed(request)
            if response.error.code:
                raise RuntimeError(response.error.message)
            checksum += len(response.embeddings)
            if response.embeddings:
                checksum += response.embeddings[-1].values[-1]
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
        if runtime.input_type_names:
            input_type_name = runtime.input_type_names[-1]

    return {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "elapsed_ms_min": round(min(elapsed_samples), 6),
        "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        "input_count": float(input_count),
        "dimensions": float(dimensions),
        "checksum": round(checksum, 6),
        "runtime_input_is_list": 1.0 if input_type_name == "list" else 0.0,
        "runtime_input_is_view": 0.0 if input_type_name == "list" else 1.0,
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_EMBEDDING_CORE_INPUTS_ITERATIONS", "150"))
    sample_count = int(os.environ.get("MELIX_EMBEDDING_CORE_INPUTS_SAMPLES", "5"))
    input_count = int(os.environ.get("MELIX_EMBEDDING_CORE_INPUTS_COUNT", "4096"))
    dimensions = int(os.environ.get("MELIX_EMBEDDING_CORE_INPUTS_DIMENSIONS", "4"))
    print(json.dumps(measure(iterations, sample_count, input_count, dimensions), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
