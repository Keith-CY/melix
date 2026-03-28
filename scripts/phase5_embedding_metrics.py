from __future__ import annotations

from statistics import mean
from time import perf_counter

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services() -> tuple[WorkerRuntimeService, WorkerInferenceService]:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    return WorkerRuntimeService(registry), WorkerInferenceService(registry)


def main() -> None:
    runtime_service, inference_service = build_services()
    load = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_embedding_model()),
        context=None,
    )
    if not load.ok:
        raise SystemExit(load.error.message or "failed to load dev embedding model")

    handle = load.model_handle

    for batch_size in (1, 4, 16):
        samples: list[float] = []
        vector_dim = 0

        for _ in range(20):
            inputs = [f"embed-{batch_size}-{index}" for index in range(batch_size)]
            request = inference_pb2.EmbedRequest(
                id=common_pb2.RequestIdentity(request_id=f"embed-{batch_size}"),
                model_handle=handle,
                inputs=inputs,
            )

            started = perf_counter()
            response = inference_service.Embed(request, context=None)
            elapsed_ms = (perf_counter() - started) * 1000.0
            samples.append(elapsed_ms)

            if response.error.code:
                raise SystemExit(response.error.message or response.error.code)
            if response.embeddings:
                vector_dim = len(response.embeddings[0].values)

        average_ms = mean(samples)
        rows_per_second = batch_size / (average_ms / 1000.0) if average_ms else 0.0
        print(
            f"batch_size={batch_size} "
            f"embed_ms={average_ms:.3f} "
            f"vector_dim={vector_dim} "
            f"rows_per_second={rows_per_second:.2f}"
        )


if __name__ == "__main__":
    main()
