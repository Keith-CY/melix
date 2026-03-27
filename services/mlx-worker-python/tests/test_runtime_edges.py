from __future__ import annotations

import runpy
from argparse import Namespace
from threading import Event

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService, build_server, main
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeUnavailableError


class FakeBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec):
        return 4096

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        if prompt == "explode":
            raise RuntimeError("backend exploded")
        yield "token-1"
        if cancel_event.is_set():
            return
        yield "token-2"


class FailingBackend(FakeBackend):
    def load_model(self, model_spec):
        raise RuntimeError("cannot load model")


def build_registry(backend=None) -> WorkerRegistry:
    return WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend or FakeBackend()),
        model_catalog=WorkerModelCatalog(),
    )


def build_services(backend=None):
    registry = build_registry(backend=backend)
    return registry, WorkerRuntimeService(registry), WorkerInferenceService(registry)


def load_default_model(runtime_service: WorkerRuntimeService) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_runtime_service_handles_failures_and_state_transitions() -> None:
    failing_registry, failing_runtime_service, _ = build_services(backend=FailingBackend())
    _ = failing_registry

    failed = failing_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    assert failed.ok is False
    assert failed.error.code == "load_failed"

    registry, runtime_service, _ = build_services()
    model_handle = load_default_model(runtime_service)

    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None)
    assert stats.stats.worker_state == "idle"
    assert stats.stats.resident_bytes == 4096

    drained = runtime_service.Drain(
        runtime_pb2.DrainRequest(stop_accepting_new=True),
        context=None,
    )
    assert drained.ok is True
    draining_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None)
    assert draining_stats.stats.worker_state == "draining"

    found = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle=model_handle),
        context=None,
    )
    missing = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle="missing-handle"),
        context=None,
    )
    warmup = runtime_service.WarmupModel(
        runtime_pb2.WarmupModelRequest(model_handle=model_handle),
        context=None,
    )
    shutdown = runtime_service.Shutdown(
        runtime_pb2.ShutdownRequest(flush_l2=True),
        context=None,
    )

    assert found.ok is True
    assert missing.ok is False
    assert missing.error.code == "not_found"
    assert warmup.ok is False
    assert warmup.error.code == "unimplemented"
    assert shutdown.ok is True
    assert registry.list_loaded_models() == []


def test_registry_capabilities_and_request_lifecycle() -> None:
    registry = build_registry()

    capabilities = registry.capabilities()
    assert capabilities.cache.supports_prefix_cache is True
    assert capabilities.cache.kv_quant_profiles == ["q4"]
    assert capabilities.execution.supports_continuous_batching is False

    state = registry.start_request("req-1")
    assert registry.get_request("req-1") is state
    assert registry.abort_request("req-1") is True
    assert state.cancel_event.is_set() is True
    assert registry.abort_request("missing") is False

    registry.finish_request("req-1")
    assert registry.get_request("req-1") is None


def test_runtime_wrapper_and_unavailable_backend_paths() -> None:
    runtime = MLXTextRuntime(backend=FakeBackend())
    prompt = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="hello"),
                    common_pb2.MessagePart(image_uri="file://ignored"),
                ],
            ),
            common_pb2.ChatMessage(
                role="assistant",
                parts=[common_pb2.MessagePart(text="world")],
            ),
        ]
    )

    assert runtime.runtime_name == "fake-mlx"
    assert prompt == "hello\nworld"
    assert runtime.estimate_resident_bytes(WorkerModelCatalog.dev_text_model()) == 4096

    unavailable = AutoMLXBackend()
    assert unavailable.estimate_resident_bytes(WorkerModelCatalog.dev_text_model()) == 0
    if unavailable.runtime_name == "mlx-unavailable":
        with pytest.raises(RuntimeUnavailableError):
            unavailable.load_model(WorkerModelCatalog.dev_text_model())
        with pytest.raises(RuntimeUnavailableError):
            list(
                unavailable.generate_tokens(
                    {},
                    "prompt",
                    common_pb2.SamplingConfig(),
                    Event(),
                )
            )


def test_inference_service_covers_error_and_unimplemented_paths() -> None:
    _, runtime_service, inference_service = build_services()
    model_handle = load_default_model(runtime_service)

    missing_model_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-missing-model"),
                    model_handle="missing-handle",
                )
            ),
            context=None,
        )
    )
    assert missing_model_events[0].error.error.code == "not_found"

    runtime_error_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-runtime-error"),
                    model_handle=model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="explode")],
                    )
                ],
                sampling=common_pb2.SamplingConfig(max_output_tokens=4),
            ),
            context=None,
        )
    )
    assert runtime_error_events[-1].error.error.code == "runtime_error"

    decode_events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-decode"),
                    model_handle=model_handle,
                )
            ),
            context=None,
        )
    )
    assert decode_events[0].error.error.code == "unimplemented"

    abort_response = inference_service.Abort(
        inference_pb2.AbortRequest(request_id="missing-request"),
        context=None,
    )
    assert abort_response.ok is False
    assert abort_response.found is False

    embed = inference_service.Embed(inference_pb2.EmbedRequest(), context=None)
    rerank = inference_service.Rerank(inference_pb2.RerankRequest(), context=None)
    transcribe = inference_service.Transcribe(inference_pb2.TranscribeRequest(), context=None)
    image_generate = inference_service.ImageGenerate(inference_pb2.ImageGenerateRequest(), context=None)
    image_edit = inference_service.ImageEdit(inference_pb2.ImageEditRequest(), context=None)

    assert embed.error.code == "unimplemented"
    assert rerank.error.code == "unimplemented"
    assert transcribe.error.code == "unimplemented"
    assert image_generate.error.code == "unimplemented"
    assert image_edit.error.code == "unimplemented"


def test_build_server_and_main_bootstrap(monkeypatch) -> None:
    registry = build_registry()
    seen_build = {}

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            seen_build["handlers"] = seen_build.get("handlers", 0) + len(handlers)

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            services = seen_build.setdefault("registered_services", [])
            services.append((service_name, len(handlers)))

        def add_insecure_port(self, address: str) -> int:
            seen_build["address"] = address
            return 1

        def stop(self, grace: int) -> None:
            seen_build["stopped"] = grace

    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())
    server, runtime_service, inference_service = build_server("/tmp/melix-test.sock", registry=registry)
    server.stop(0)

    assert isinstance(runtime_service, WorkerRuntimeService)
    assert isinstance(inference_service, WorkerInferenceService)
    assert seen_build == {
        "handlers": 2,
        "registered_services": [
            ("melix.worker.v1.RuntimeService", 8),
            ("melix.worker.v1.InferenceService", 9),
        ],
        "address": "unix:///tmp/melix-test.sock",
        "stopped": 0,
    }

    seen = {}

    class FakeServer:
        def start(self):
            seen["started"] = True

        def wait_for_termination(self):
            seen["waited"] = True

    def fake_build_server(socket_path: str, backend_mode: str = "auto"):
        seen["socket_path"] = socket_path
        seen["backend_mode"] = backend_mode
        return FakeServer(), None, None

    monkeypatch.setattr("worker.grpc_server.build_server", fake_build_server)
    monkeypatch.setattr("argparse.ArgumentParser.parse_args", lambda self: Namespace(socket_path="/tmp/from-main.sock"))
    main()

    assert seen == {
        "backend_mode": "auto",
        "socket_path": "/tmp/from-main.sock",
        "started": True,
        "waited": True,
    }


def test_bootstrap_module_invokes_grpc_main(monkeypatch) -> None:
    called = {"count": 0}

    def fake_main() -> None:
        called["count"] += 1

    monkeypatch.setattr("worker.grpc_server.main", fake_main)
    runpy.run_module("worker.bootstrap", run_name="__main__")

    assert called["count"] == 1
