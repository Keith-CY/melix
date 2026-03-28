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
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_rerank_model()),
        context=None,
    )
    if not load.ok:
        raise SystemExit(load.error.message or "failed to load dev rerank model")

    handle = load.model_handle

    for document_count in (4, 16, 64):
        samples: list[float] = []
        top_k = 5

        for _ in range(20):
            request = inference_pb2.RerankRequest(
                id=common_pb2.RequestIdentity(request_id=f"rerank-{document_count}"),
                model_handle=handle,
                query="swift worker runtime control plane",
                documents=[f"document {index} swift worker runtime" for index in range(document_count)],
                top_k=top_k,
            )

            started = perf_counter()
            response = inference_service.Rerank(request, context=None)
            elapsed_ms = (perf_counter() - started) * 1000.0
            samples.append(elapsed_ms)

            if response.error.code:
                raise SystemExit(response.error.message or response.error.code)

        average_ms = mean(samples)
        docs_per_second = document_count / (average_ms / 1000.0) if average_ms else 0.0
        print(
            f"document_count={document_count} "
            f"top_k={top_k} "
            f"rerank_ms={average_ms:.3f} "
            f"docs_per_second={docs_per_second:.2f}"
        )


if __name__ == "__main__":
    main()
