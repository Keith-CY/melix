from packages.protocol.python.worker.v1 import common_pb2, runtime_pb2

from worker.grpc_server import WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class FakeBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_runtime_service() -> WorkerRuntimeService:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FakeBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    return WorkerRuntimeService(registry)


def test_handshake_reports_protocol_and_capabilities() -> None:
    service = build_runtime_service()

    response = service.Handshake(
        runtime_pb2.HandshakeRequest(
            protocol_version="melix.worker.v1",
            worker_id="worker-text-001",
            controlplane_instance_id="controlplane-1",
        ),
        context=None,
    )

    assert response.protocol_version == "melix.worker.v1"
    assert response.runtime_version == "fake-mlx"
    assert response.capabilities.cache.supports_prefix_cache is True


def test_load_model_returns_handle_and_lists_model() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_text_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )

    assert response.ok is True
    assert response.model_handle.startswith("melix-dev-text::")

    listed = service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(),
        context=None,
    )

    assert listed.model_handles == [response.model_handle]


def test_load_model_returns_residency_contract_and_loaded_model_summaries() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_text_model(),
            memory_budget_bytes=4096,
            pin_on_load=True,
        ),
        context=None,
    )

    assert response.ok is True
    assert response.residency.state == common_pb2.RESIDENCY_STATE_PINNED
    assert response.residency.pin_requested is True
    assert response.residency.pinned is True
    assert response.residency.policy == common_pb2.MEMORY_RESIDENCY_PINNED

    listed = service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(),
        context=None,
    )

    assert listed.model_handles == [response.model_handle]
    assert len(listed.loaded_models) == 1
    assert listed.loaded_models[0].model_handle == response.model_handle
    assert listed.loaded_models[0].model.model_id == "melix-dev-text"
    assert listed.loaded_models[0].residency.state == common_pb2.RESIDENCY_STATE_PINNED
    assert listed.loaded_models[0].residency.pinned is True


def test_load_model_supports_embedding_models() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_embedding_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )

    assert response.ok is True
    assert response.model_handle.startswith("melix-dev-embed::")


def test_load_model_supports_rerank_models() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_rerank_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )

    assert response.ok is True
    assert response.model_handle.startswith("melix-dev-rerank::")


def test_load_model_supports_ocr_and_vlm_models() -> None:
    service = build_runtime_service()

    ocr = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_ocr_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )
    vlm = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_vlm_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )

    assert ocr.ok is True
    assert vlm.ok is True
    assert ocr.model_handle.startswith("melix-dev-ocr::")
    assert vlm.model_handle.startswith("melix-dev-vlm::")


def test_load_model_supports_transcription_and_speech_models() -> None:
    service = build_runtime_service()

    transcription = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_transcription_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )
    speech = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_speech_model(),
            memory_budget_bytes=4096,
        ),
        context=None,
    )

    assert transcription.ok is True
    assert speech.ok is True
    assert transcription.model_handle.startswith("melix-dev-transcribe::")
    assert speech.model_handle.startswith("melix-dev-speech::")


def test_handshake_reports_phase_six_multimodal_capabilities() -> None:
    service = build_runtime_service()

    response = service.Handshake(
        runtime_pb2.HandshakeRequest(
            protocol_version="melix.worker.v1",
            worker_id="worker-text-001",
            controlplane_instance_id="controlplane-1",
        ),
        context=None,
    )

    assert response.capabilities.multimodal.supports_ocr is True
    assert response.capabilities.multimodal.supports_vlm is True
    assert response.capabilities.multimodal.supports_transcription is True
    assert response.capabilities.multimodal.supports_speech is True
