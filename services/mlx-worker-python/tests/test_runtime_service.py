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
    assert response.capabilities.execution.supports_disk_streaming is False


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
    assert response.residency.effective_disk_streaming_mode == common_pb2.DISK_STREAMING_DISABLED

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


def test_load_model_rejects_unsupported_disk_streaming_mode() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=WorkerModelCatalog.dev_text_model(),
            disk_streaming_mode=common_pb2.DISK_STREAMING_REQUIRE_DISK,
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "disk_streaming_unsupported"
    assert response.error.details["model_id"] == "melix-dev-text"
    assert response.error.details["requested_mode"] == "DISK_STREAMING_REQUIRE_DISK"


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


def test_load_model_prefers_explicit_request_spec_over_seed_catalog_model() -> None:
    service = build_runtime_service()
    request_model = WorkerModelCatalog.dev_image_model(
        {
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/flux-fill-dev",
        }
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=request_model,
        ),
        context=None,
    )

    assert response.ok is True
    listed = service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(),
        context=None,
    )

    assert listed.loaded_models[0].model.model_path == "models/flux-fill-dev"
    assert listed.loaded_models[0].model.ext["melix.image.family_id"] == "fill-v1"
    assert listed.loaded_models[0].model.ext["melix.image.supports_generation"] == "false"
    assert listed.loaded_models[0].model.ext["melix.image.supports_edit"] == "true"


def test_load_model_uses_catalog_model_for_sparse_requests() -> None:
    service = build_runtime_service()

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=common_pb2.ModelSpec(model_id="melix-dev-text"),
        ),
        context=None,
    )

    assert response.ok is True
    listed = service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(),
        context=None,
    )
    assert listed.loaded_models[0].model.model_path == "models/melix-dev-text"


def test_load_model_uses_requested_spec_when_catalog_has_no_match() -> None:
    service = build_runtime_service()
    request_model = common_pb2.ModelSpec(
        model_id="custom-dev-text",
        model_path="models/custom-dev-text",
        model_kind="text",
        revision="dev",
        tokenizer_hash="tok-custom-dev",
        quant_profile_id="q8",
        parser_mode="text",
        reasoning_mode="off",
        max_context=4096,
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=request_model),
        context=None,
    )

    assert response.ok is True
    listed = service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(),
        context=None,
    )
    assert listed.loaded_models[0].model.model_id == "custom-dev-text"
    assert listed.loaded_models[0].model.model_path == "models/custom-dev-text"


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
