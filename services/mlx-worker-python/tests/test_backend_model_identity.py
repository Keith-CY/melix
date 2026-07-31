from __future__ import annotations

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


class GuardOnlyRegistry:
    """Expose only the public identity guard and fail if runtime dispatch begins."""

    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry
        self.runtime_dispatch_count = 0

    def validate_backend_identity(self, handle, requested):
        return self._registry.validate_backend_identity(handle, requested)

    def get_loaded_model(self, handle):
        self.runtime_dispatch_count += 1
        raise AssertionError(f"runtime dispatched for {handle}")


def _identity(
    model_id: str,
    *,
    adapter_id: str = "adapter-alpha",
    generation: int = 7,
    worker_instance_id: str = "worker-text-001",
):
    return common_pb2.BackendModelIdentity(
        requested_model_id=model_id,
        requested_adapter_id=adapter_id,
        route_generation=generation,
        worker_instance_id=worker_instance_id,
    )


def _services():
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    guard_registry = GuardOnlyRegistry(registry)
    return (
        registry,
        WorkerRuntimeService(registry),
        WorkerInferenceService(guard_registry),
        guard_registry,
    )


def _load(runtime_service: WorkerRuntimeService) -> str:
    model = WorkerModelCatalog.dev_text_model()
    model.ext["melix.adapter_set_hash"] = "adapter-alpha"
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=model,
            backend_identity=_identity(model.model_id),
        ),
        context=None,
    )
    assert response.ok
    return response.model_handle


def _assert_mismatch(error: common_pb2.ErrorStatus) -> None:
    assert error.code == "model_identity_mismatch"
    assert error.retriable is True
    assert error.details["requested_route_generation"] == "6"
    assert error.details["loaded_route_generation"] == "7"
    assert error.backend_identity_mismatch.mismatch_reason == (
        "model_id,adapter_id,route_generation"
    )
    assert "melix-dev-text" not in error.message
    assert "wrong-model" not in error.message


def test_backend_identity_mismatch_rejects_every_python_inference_modality_before_runtime_work() -> (
    None
):
    registry, runtime_service, inference_service, guard_registry = _services()
    handle = _load(runtime_service)
    wrong = _identity("wrong-model", adapter_id="wrong-adapter", generation=6)

    generate_fixtures = [
        common_pb2.MessagePart(text="text payload"),
        common_pb2.MessagePart(image_bytes=b"image payload"),
        common_pb2.MessagePart(audio_bytes=b"audio payload"),
        common_pb2.MessagePart(video_bytes=b"video payload"),
        common_pb2.MessagePart(text="tool-adjacent payload"),
    ]
    for index, part in enumerate(generate_fixtures):
        execution = inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=f"identity-generate-{index}"),
            model_handle=handle,
            backend_identity=wrong,
        )
        if index == len(generate_fixtures) - 1:
            execution.tool_config.tools.add(
                name="lookup",
                description="lookup fixture",
                json_schema='{"type":"object"}',
            )
        generate_events = list(
            inference_service.Generate(
                inference_pb2.GenerateRequest(
                    execution=execution,
                    messages=[common_pb2.ChatMessage(role="user", parts=[part])],
                ),
                context=None,
            )
        )
        assert len(generate_events) == 1
        _assert_mismatch(generate_events[0].error.error)
        assert generate_events[0].WhichOneof("payload") == "error"

    execution = inference_pb2.ExecutionMetadata(
        id=common_pb2.RequestIdentity(request_id="identity-phased"),
        model_handle=handle,
        backend_identity=wrong,
    )

    prefill = inference_service.Prefill(
        inference_pb2.PrefillRequest(execution=execution),
        context=None,
    )
    _assert_mismatch(prefill.error)

    decode_events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(execution=execution, decode_handle="stale"),
            context=None,
        )
    )
    assert len(decode_events) == 1
    _assert_mismatch(decode_events[0].error.error)

    embed = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="identity-embed"),
            model_handle=handle,
            inputs=["payload"],
            backend_identity=wrong,
        ),
        context=None,
    )
    assert embed.embeddings == []
    _assert_mismatch(embed.error)

    rerank = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="identity-rerank"),
            model_handle=handle,
            query="query",
            documents=["document"],
            backend_identity=wrong,
        ),
        context=None,
    )
    assert rerank.items == []
    _assert_mismatch(rerank.error)

    transcribe = inference_service.Transcribe(
        inference_pb2.TranscribeRequest(
            id=common_pb2.RequestIdentity(request_id="identity-transcribe"),
            model_handle=handle,
            audio_bytes=b"audio",
            backend_identity=wrong,
        ),
        context=None,
    )
    assert transcribe.text == ""
    _assert_mismatch(transcribe.error)

    speak_request = inference_pb2.SpeakRequest(
        id=common_pb2.RequestIdentity(request_id="identity-speak"),
        model_handle=handle,
        input="hello",
        backend_identity=wrong,
    )
    speak = inference_service.Speak(speak_request, context=None)
    assert speak.audio_bytes == b""
    _assert_mismatch(speak.error)

    speak_events = list(inference_service.SpeakStream(speak_request, context=None))
    assert len(speak_events) == 1
    assert speak_events[0].kind == inference_pb2.SPEAK_STREAM_EVENT_KIND_ERROR
    assert speak_events[0].audio_bytes == b""
    _assert_mismatch(speak_events[0].error)

    image_generate = inference_service.ImageGenerate(
        inference_pb2.ImageGenerateRequest(
            id=common_pb2.RequestIdentity(request_id="identity-image-generate"),
            model_handle=handle,
            prompt="image",
            backend_identity=wrong,
        ),
        context=None,
    )
    assert image_generate.images == []
    _assert_mismatch(image_generate.error)

    image_edit = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="identity-image-edit"),
            model_handle=handle,
            prompt="edit",
            image=b"image",
            backend_identity=wrong,
        ),
        context=None,
    )
    assert image_edit.images == []
    _assert_mismatch(image_edit.error)

    loaded = runtime_service.ListLoadedModels(
        runtime_pb2.ListLoadedModelsRequest(), context=None
    ).loaded_models
    assert len(loaded) == 1
    assert loaded[0].backend_identity == _identity("melix-dev-text")

    stats = registry.runtime_stats()
    assert stats.model_identity_mismatch_count == 14
    receipt = stats.last_model_identity_mismatch
    assert receipt.requested_model_id == "wrong-model"
    assert receipt.loaded_model_id == "melix-dev-text"
    assert receipt.requested_adapter_id == "wrong-adapter"
    assert receipt.loaded_adapter_id == "adapter-alpha"
    assert receipt.requested_route_generation == 6
    assert receipt.loaded_route_generation == 7
    assert receipt.requested_worker_instance_id == "worker-text-001"
    assert receipt.loaded_worker_instance_id == "worker-text-001"
    assert receipt.mismatch_reason == "model_id,adapter_id,route_generation"
    assert guard_registry.runtime_dispatch_count == 0


def test_backend_identity_missing_is_typed_for_identity_bound_loads() -> None:
    _, runtime_service, inference_service, guard_registry = _services()
    handle = _load(runtime_service)

    response = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="identity-missing"),
            model_handle=handle,
            inputs=["payload"],
        ),
        context=None,
    )

    assert response.embeddings == []
    assert response.error.code == "model_identity_missing"
    assert response.error.retriable is False
    assert (
        response.error.backend_identity_mismatch.mismatch_reason == "identity_missing"
    )
    assert guard_registry.runtime_dispatch_count == 0


def test_complete_backend_identity_with_unknown_handle_is_retriable_before_runtime_work() -> (
    None
):
    registry, _, inference_service, guard_registry = _services()
    requested = _identity("melix-dev-text", generation=9)
    events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="identity-restart"),
                    model_handle="stale-before-worker-restart",
                    backend_identity=requested,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="must not run")],
                    )
                ],
            ),
            context=None,
        )
    )

    assert len(events) == 1
    error = events[0].error.error
    assert error.code == "model_identity_mismatch"
    assert error.retriable is True
    assert error.backend_identity_mismatch.mismatch_reason == "model_handle_missing"
    assert error.backend_identity_mismatch.requested_model_id == "melix-dev-text"
    assert error.backend_identity_mismatch.loaded_model_id == ""
    assert error.backend_identity_mismatch.requested_route_generation == 9
    assert error.backend_identity_mismatch.loaded_route_generation == 0
    assert registry.runtime_stats().model_identity_mismatch_count == 1
    assert guard_registry.runtime_dispatch_count == 0


def test_loaded_identity_uses_resolved_model_and_adapter_not_claimed_load_identity() -> (
    None
):
    registry, runtime_service, inference_service, guard_registry = _services()
    model = WorkerModelCatalog.dev_text_model()
    model.ext["melix.adapter_set_hash"] = "adapter-alpha"
    claimed = _identity("wrong-model", adapter_id="wrong-adapter", generation=11)
    loaded = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model, backend_identity=claimed),
        context=None,
    )
    assert loaded.ok

    response = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="identity-load-claim"),
            model_handle=loaded.model_handle,
            inputs=["must not run"],
            backend_identity=claimed,
        ),
        context=None,
    )

    assert response.embeddings == []
    assert response.error.code == "model_identity_mismatch"
    assert response.error.retriable is True
    assert (
        response.error.backend_identity_mismatch.mismatch_reason
        == "model_id,adapter_id"
    )
    assert response.error.backend_identity_mismatch.requested_model_id == "wrong-model"
    assert (
        response.error.backend_identity_mismatch.requested_adapter_id == "wrong-adapter"
    )
    assert response.error.backend_identity_mismatch.loaded_model_id == "melix-dev-text"
    assert response.error.backend_identity_mismatch.loaded_adapter_id == "adapter-alpha"
    assert response.error.backend_identity_mismatch.loaded_route_generation == 11
    assert guard_registry.runtime_dispatch_count == 0


def test_backend_identity_rejects_worker_instance_mismatch_before_runtime_work() -> (
    None
):
    registry, runtime_service, inference_service, guard_registry = _services()
    handle = _load(runtime_service)

    response = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="identity-worker-replaced"),
            model_handle=handle,
            inputs=["must not run"],
            backend_identity=_identity(
                "melix-dev-text",
                worker_instance_id="replacement-worker",
            ),
        ),
        context=None,
    )

    assert response.embeddings == []
    assert response.error.code == "model_identity_mismatch"
    assert response.error.retriable is True
    receipt = response.error.backend_identity_mismatch
    assert receipt.mismatch_reason == "worker_instance_id"
    assert receipt.requested_worker_instance_id == "replacement-worker"
    assert receipt.loaded_worker_instance_id == "worker-text-001"
    assert registry.runtime_stats().model_identity_mismatch_count == 1
    assert guard_registry.runtime_dispatch_count == 0


def test_backend_identity_diagnostics_preserve_public_ids_and_redact_local_paths() -> (
    None
):
    registry, _, _, _ = _services()
    model = WorkerModelCatalog.dev_text_model()
    model.model_id = "/Users/operator/private/model"
    model.ext["melix.adapter_set_hash"] = "file:///Users/operator/private/adapter"
    bound_identity = _identity(
        model.model_id,
        adapter_id=model.ext["melix.adapter_set_hash"],
        generation=4,
    )
    loaded = registry.load_model(
        model,
        backend_identity=bound_identity,
    )

    missing_handle = registry.validate_backend_identity(
        "missing-handle", bound_identity
    )
    assert missing_handle is not None
    assert missing_handle.code == "model_identity_mismatch"
    assert missing_handle.retriable is True
    assert (
        missing_handle.backend_identity_mismatch.mismatch_reason
        == "model_handle_missing"
    )
    assert registry.validate_backend_identity(loaded.handle, bound_identity) is None
    error = registry.validate_backend_identity(
        loaded.handle,
        _identity("public-catalog/model", adapter_id="~/private/adapter", generation=3),
    )
    receipt = registry.runtime_stats().last_model_identity_mismatch

    assert error is not None
    assert error.code == "model_identity_mismatch"
    assert receipt.requested_model_id == "public-catalog/model"
    assert receipt.loaded_model_id == "[local-path-redacted]"
    assert receipt.requested_adapter_id == "[local-path-redacted]"
    assert receipt.loaded_adapter_id == "[local-path-redacted]"
    assert receipt.mismatch_reason == "model_id,adapter_id,route_generation"

    long_id = "catalog/" + ("x" * 160)
    assert (
        registry.validate_backend_identity(
            loaded.handle,
            _identity(long_id, adapter_id="public-adapter", generation=3),
        )
        is not None
    )
    assert registry.runtime_stats().last_model_identity_mismatch.requested_model_id == (
        long_id[:125] + "..."
    )

    for local_path in (
        "../private/model",
        "FILE:///private/model",
        r"\\server\share\model",
    ):
        assert (
            registry.validate_backend_identity(
                loaded.handle,
                _identity(local_path, adapter_id="public-adapter", generation=3),
            )
            is not None
        )
        assert (
            registry.runtime_stats().last_model_identity_mismatch.requested_model_id
            == "[local-path-redacted]"
        )

    legacy_registry, _, _, _ = _services()
    legacy_loaded = legacy_registry.load_model(model)
    assert legacy_loaded.backend_identity.requested_model_id == model.model_id
    assert legacy_loaded.backend_identity.route_generation == 0
