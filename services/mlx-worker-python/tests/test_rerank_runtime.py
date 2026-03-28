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


def build_services():
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    return runtime_service, inference_service


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_rerank_returns_sorted_scores_and_honors_top_k() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_rerank_model())

    first = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-1"),
            model_handle=model_handle,
            query="swift control plane runtime",
            documents=[
                "swift control plane runtime",
                "embedding worker batch path",
                "control plane swift worker route",
            ],
            top_k=2,
        ),
        context=None,
    )
    second = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-2"),
            model_handle=model_handle,
            query="swift control plane runtime",
            documents=[
                "swift control plane runtime",
                "embedding worker batch path",
                "control plane swift worker route",
            ],
            top_k=2,
        ),
        context=None,
    )

    assert first.error.code == ""
    assert len(first.items) == 2
    assert first.items[0].score >= first.items[1].score
    assert first.items[0].index == second.items[0].index
    assert first.items[1].index == second.items[1].index
    assert first.items[0].score == second.items[0].score
    assert first.items[1].score == second.items[1].score


def test_rerank_rejects_missing_and_wrong_model_kinds() -> None:
    runtime_service, inference_service = build_services()
    text_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    missing = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-missing"),
            model_handle="missing-handle",
            query="swift",
            documents=["swift worker"],
            top_k=1,
        ),
        context=None,
    )
    wrong_kind = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="rerank-text"),
            model_handle=text_handle,
            query="swift",
            documents=["swift worker"],
            top_k=1,
        ),
        context=None,
    )

    assert missing.error.code == "not_found"
    assert wrong_kind.error.code == "invalid_argument"
