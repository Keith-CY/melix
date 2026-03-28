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


def test_embed_returns_stable_vectors_for_loaded_embedding_models() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_embedding_model())

    first = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-1"),
            model_handle=model_handle,
            inputs=["alpha", "beta"],
        ),
        context=None,
    )
    second = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-2"),
            model_handle=model_handle,
            inputs=["alpha", "beta"],
        ),
        context=None,
    )

    assert first.error.code == ""
    assert len(first.embeddings) == 2
    assert len(first.embeddings[0].values) == 8
    assert len(first.embeddings[1].values) == 8
    assert first.embeddings[0].values == second.embeddings[0].values
    assert first.embeddings[1].values == second.embeddings[1].values
    assert first.embeddings[0].values != first.embeddings[1].values


def test_embed_rejects_missing_and_wrong_model_kinds() -> None:
    runtime_service, inference_service = build_services()
    text_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    missing = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-missing"),
            model_handle="missing-handle",
            inputs=["alpha"],
        ),
        context=None,
    )
    wrong_kind = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="embed-text"),
            model_handle=text_handle,
            inputs=["alpha"],
        ),
        context=None,
    )

    assert missing.error.code == "not_found"
    assert wrong_kind.error.code == "invalid_argument"
