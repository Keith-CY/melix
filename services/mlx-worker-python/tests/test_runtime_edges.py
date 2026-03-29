from __future__ import annotations

import json
import runpy
from argparse import Namespace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.grpc_server import (
    BootstrapMetricsExporter,
    WorkerInferenceService,
    WorkerMaintenanceService,
    WorkerRuntimeService,
    build_server,
    main,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_delay import configured_delay_ms
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

    vision_state = registry.start_request("req-vision", runtime_kind="ocr")
    transcription_state = registry.start_request("req-transcription", runtime_kind="transcription")
    speech_state = registry.start_request("req-speech", runtime_kind="speech")
    assert vision_state.runtime_kind == "ocr"
    assert transcription_state.runtime_kind == "transcription"
    assert speech_state.runtime_kind == "speech"

    registry.record_vision_probe(
        "ocr",
        SimpleNamespace(
            preprocess_latency_ms=12.0,
            preprocess_input_bytes=64,
            preprocess_peak_memory_bytes=2048,
            first_token_latency_ms=5.0,
        ),
    )
    vision_stats = registry.runtime_stats()
    assert vision_stats.active_multimodal_requests == 3
    assert vision_stats.last_probe_kind == "ocr"
    assert vision_stats.last_preprocess_latency_ms == 12.0
    assert vision_stats.last_preprocess_input_bytes == 64
    assert vision_stats.last_preprocess_peak_memory_bytes == 2048
    assert vision_stats.last_first_token_latency_ms == 5.0

    registry.record_transcription_probe(
        SimpleNamespace(
            preprocess_latency_ms=18.0,
            preprocess_input_bytes=96,
            preprocess_peak_memory_bytes=4096,
            transcription_latency_ms=9.0,
            estimated_duration_seconds=0.75,
            chunk_count=4,
        )
    )
    transcription_stats = registry.runtime_stats()
    assert transcription_stats.last_probe_kind == "transcription"
    assert transcription_stats.last_transcription_latency_ms == 9.0
    assert transcription_stats.last_audio_duration_seconds == 0.75
    assert transcription_stats.last_audio_chunk_count == 4

    registry.record_speech_probe(
        SimpleNamespace(
            speech_latency_ms=7.5,
            output_bytes=128,
        )
    )
    speech_stats = registry.runtime_stats()
    assert speech_stats.last_probe_kind == "speech"
    assert speech_stats.last_speech_latency_ms == 7.5
    assert speech_stats.last_audio_output_bytes == 128
    assert speech_stats.last_image_job_latency_ms == 0.0

    registry.record_image_probe(
        SimpleNamespace(
            job_latency_ms=42.5,
            artifact_publish_ms=3.25,
            output_bytes=512,
            peak_memory_bytes=40960,
        )
    )
    image_stats = registry.runtime_stats()
    assert image_stats.last_probe_kind == "image"
    assert image_stats.last_image_job_latency_ms == 42.5
    assert image_stats.last_image_artifact_publish_ms == 3.25
    assert image_stats.last_image_output_bytes == 512
    assert image_stats.last_image_peak_memory_bytes == 40960

    registry.finish_request("req-vision")
    registry.finish_request("req-transcription")
    registry.finish_request("req-speech")
    assert registry.runtime_stats().active_multimodal_requests == 0


def test_deterministic_multimodal_delay_prefers_specific_keys_and_shared_fallback() -> None:
    assert configured_delay_ms("transcription", {}) == 0.0
    assert configured_delay_ms("transcription", {"MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS": "25"}) == 25.0
    assert configured_delay_ms(
        "transcription",
        {
            "MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS": "25",
            "MELIX_DETERMINISTIC_TRANSCRIPTION_DELAY_MS": "150",
        },
    ) == 150.0
    assert configured_delay_ms("ocr", {"MELIX_DETERMINISTIC_OCR_DELAY_MS": "invalid"}) == 0.0


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

    embed_model = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_embedding_model()),
        context=None,
    )
    assert embed_model.ok is True

    embed = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="req-embed"),
            model_handle=embed_model.model_handle,
            inputs=["one", "two"],
        ),
        context=None,
    )
    rerank_model = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_rerank_model()),
        context=None,
    )
    assert rerank_model.ok is True

    rerank = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="req-rerank"),
            model_handle=rerank_model.model_handle,
            query="swift runtime worker",
            documents=["swift runtime worker", "image generation", "embedding vector"],
            top_k=2,
        ),
        context=None,
    )
    transcribe = inference_service.Transcribe(inference_pb2.TranscribeRequest(), context=None)
    speak = inference_service.Speak(inference_pb2.SpeakRequest(), context=None)
    image_generate = inference_service.ImageGenerate(inference_pb2.ImageGenerateRequest(), context=None)
    image_edit = inference_service.ImageEdit(inference_pb2.ImageEditRequest(), context=None)

    assert embed.error.code == ""
    assert len(embed.embeddings) == 2
    assert rerank.error.code == ""
    assert len(rerank.items) == 2
    assert transcribe.error.code == "not_found"
    assert speak.error.code == "not_found"
    assert image_generate.error.code == "not_found"
    assert image_edit.error.code == "not_found"
    assert image_generate.job.state == common_pb2.IMAGE_JOB_FAILED
    assert image_generate.job.operation == "image_generate"
    assert image_edit.job.state == common_pb2.IMAGE_JOB_FAILED
    assert image_edit.job.operation == "image_edit"


def test_build_server_and_main_bootstrap(monkeypatch, tmp_path: Path) -> None:
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
    metrics_path = tmp_path / "python-worker-metrics.json"
    exporter = BootstrapMetricsExporter(str(metrics_path))
    server, runtime_service, inference_service = build_server(
        "/tmp/melix-test.sock",
        registry=registry,
        metrics_exporter=exporter,
    )
    server.stop(0)

    assert isinstance(runtime_service, WorkerRuntimeService)
    assert isinstance(inference_service, WorkerInferenceService)
    assert seen_build == {
        "handlers": 3,
        "registered_services": [
            ("melix.worker.v1.RuntimeService", 8),
            ("melix.worker.v1.InferenceService", 10),
            ("melix.worker.v1.MaintenanceService", 4),
        ],
        "address": f"unix://{Path('/tmp/melix-test.sock').resolve()}",
        "stopped": 0,
    }
    build_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
    assert build_metrics["python_worker.registry_init_ms"] >= 0
    assert build_metrics["python_worker.server_build_ms"] >= 0

    seen = {}

    class FakeServer:
        def start(self):
            seen["started"] = True

        def wait_for_termination(self):
            seen["waited"] = True

    def fake_build_server(
        socket_path: str,
        backend_mode: str = "auto",
        metrics_exporter: BootstrapMetricsExporter | None = None,
    ):
        seen["socket_path"] = socket_path
        seen["backend_mode"] = backend_mode
        if metrics_exporter is not None:
            metrics_exporter.set_milliseconds("python_worker.registry_init_ms", 7.0)
            metrics_exporter.set_milliseconds("python_worker.server_build_ms", 5.0)
        return FakeServer(), None, None

    monkeypatch.setattr("worker.grpc_server.build_server", fake_build_server)
    perf_counter_values = iter(
        [
            1_000_000_000,
            1_030_000_000,
            1_060_000_000,
            1_062_000_000,
            1_080_000_000,
        ]
    )
    monkeypatch.setattr("worker.grpc_server.time.perf_counter_ns", lambda: next(perf_counter_values))
    monkeypatch.setenv("MELIX_PYTHON_WORKER_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("MELIX_PYTHON_WORKER_STARTUP_T0_NS", "900000000")
    monkeypatch.setattr(
        "argparse.ArgumentParser.parse_args",
        lambda self: Namespace(socket_path="/tmp/from-main.sock", backend_mode="auto"),
    )
    main()

    assert seen == {
        "backend_mode": "auto",
        "socket_path": "/tmp/from-main.sock",
        "started": True,
        "waited": True,
    }
    main_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
    assert main_metrics["python_worker.spawn_to_bootstrap_ms"] == 100
    assert main_metrics["python_worker.arg_parse_ms"] == 30
    assert main_metrics["python_worker.registry_init_ms"] == 7
    assert main_metrics["python_worker.server_build_ms"] == 5
    assert main_metrics["python_worker.server_start_ms"] == 2
    assert main_metrics["python_worker.bootstrap_ms"] == 80


def test_build_server_normalizes_relative_socket_path(monkeypatch, tmp_path: Path) -> None:
    registry = build_registry()
    seen: dict[str, object] = {}

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            seen["handlers"] = seen.get("handlers", 0) + len(handlers)

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            services = seen.setdefault("registered_services", [])
            assert isinstance(services, list)
            services.append((service_name, len(handlers)))

        def add_insecure_port(self, address: str) -> int:
            seen["address"] = address
            return 1

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())

    build_server("relative-worker.sock", registry=registry)

    assert seen["address"] == f"unix://{tmp_path / 'relative-worker.sock'}"


def test_maintenance_service_keeps_doctor_and_bench_structured(tmp_path: Path) -> None:
    service = WorkerMaintenanceService(build_registry(), jobs_root=tmp_path / "ops")

    doctor = service.RunDoctor(
        maintenance_pb2.RunDoctorRequest(
            model_handle="melix-dev-text::1",
            include_cache_diagnostics=True,
            include_memory_report=True,
        ),
        context=None,
    )
    bench_events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(model_handle="melix-dev-text::1", suites=["smoke", "latency"]),
            context=None,
        )
    )

    assert doctor.ok is True
    assert "# Melix Doctor" in doctor.report_markdown
    assert "## Cache" in doctor.report_markdown
    assert "## Memory" in doctor.report_markdown
    assert bench_events[0].started.job_id == "model-ops-0001"
    assert any(event.HasField("metric") and event.metric.name == "bench.smoke.ttft_ms" for event in bench_events)
    assert any(event.HasField("metric") and event.metric.name == "bench.latency.p50_ms" for event in bench_events)
    assert bench_events[-1].completed.report_path.endswith("bench-report.md")


def test_bootstrap_module_invokes_grpc_main(monkeypatch) -> None:
    called = {"count": 0}

    def fake_main() -> None:
        called["count"] += 1

    monkeypatch.setattr("worker.grpc_server.main", fake_main)
    runpy.run_module("worker.bootstrap", run_name="__main__")

    assert called["count"] == 1
