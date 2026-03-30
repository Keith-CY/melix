from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from concurrent import futures
from pathlib import Path
from typing import Any

import grpc

from packages.protocol.python.worker.v1 import (
    cache_pb2,
    cache_pb2_grpc,
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    maintenance_pb2,
    maintenance_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)

from worker.engine.embedding_core import EmbeddingCore
from worker.engine.image_edit_core import ImageEditCore
from worker.engine.engine_core import EngineCore
from worker.engine.image_generation_core import ImageGenerationCore
from worker.engine.maintenance_core import MaintenanceCore
from worker.engine.rerank_core import RerankCore
from worker.engine.speech_core import SpeechCore
from worker.engine.transcription_core import TranscriptionCore
from worker.registry import MemoryBudgetExceeded, WorkerRegistry
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class BootstrapMetricsExporter:
    def __init__(self, export_path: str | None) -> None:
        self._export_path = Path(export_path).resolve() if export_path else None
        self._values: dict[str, int] = {
            "python_worker.spawn_to_bootstrap_ms": 0,
            "python_worker.arg_parse_ms": 0,
            "python_worker.registry_init_ms": 0,
            "python_worker.server_build_ms": 0,
            "python_worker.server_start_ms": 0,
            "python_worker.bootstrap_ms": 0,
        }
        self._write()

    def set_milliseconds(self, key: str, value: float) -> None:
        self._values[key] = max(0, int(round(value)))
        self._write()

    def _write(self) -> None:
        if self._export_path is None:
            return

        self._export_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "updated_at_unix_ms": int(time.time() * 1000),
            "values": self._values,
        }
        _write_json_atomically(self._export_path, payload)


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            json.dump(payload, temp_file, sort_keys=True)
        os.replace(os.fspath(temp_path), os.fspath(path))
    finally:
        temp_path.unlink(missing_ok=True)


class WorkerRuntimeService(runtime_pb2_grpc.RuntimeServiceServicer):
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def Handshake(self, request, context):
        return runtime_pb2.HandshakeResponse(
            protocol_version=request.protocol_version,
            runtime_version=self._registry.runtime.runtime_name,
            capabilities=self._registry.capabilities(),
        )

    def LoadModel(self, request, context):
        try:
            loaded = self._registry.load_model(
                request.model,
                pin_on_load=request.pin_on_load,
                memory_budget_bytes=request.memory_budget_bytes,
            )
        except MemoryBudgetExceeded as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="memory_budget_exceeded",
                    message=str(exc),
                    details=exc.details,
                ),
            )
        except Exception as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="load_failed", message=str(exc)),
            )
        response = runtime_pb2.LoadModelResponse(
            ok=True,
            model_handle=loaded.handle,
            estimated_resident_bytes=loaded.estimated_resident_bytes,
            resolved_capabilities=self._registry.capabilities(),
        )
        response.residency.CopyFrom(loaded.residency)
        return response

    def UnloadModel(self, request, context):
        found = self._registry.unload_model(request.model_handle)
        return runtime_pb2.UnloadModelResponse(
            ok=found,
            error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle.") if not found else None,
        )

    def WarmupModel(self, request, context):
        return runtime_pb2.WarmupModelResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Warmup is deferred in phase 0."),
        )

    def GetRuntimeStats(self, request, context):
        return runtime_pb2.GetRuntimeStatsResponse(stats=self._registry.runtime_stats())

    def ListLoadedModels(self, request, context):
        return runtime_pb2.ListLoadedModelsResponse(
            model_handles=self._registry.list_loaded_models(),
            loaded_models=self._registry.list_loaded_model_summaries(),
        )

    def Drain(self, request, context):
        self._registry.set_draining(request.stop_accepting_new)
        return runtime_pb2.DrainResponse(ok=True)

    def Shutdown(self, request, context):
        return runtime_pb2.ShutdownResponse(ok=True)


class WorkerInferenceService(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, registry: WorkerRegistry, images_root: Path | str | None = None) -> None:
        self._registry = registry
        self._engine = EngineCore(registry)
        self._embedding = EmbeddingCore(registry)
        self._rerank = RerankCore(registry)
        self._transcription = TranscriptionCore(registry)
        self._speech = SpeechCore(registry)
        self._image_generation = ImageGenerationCore(registry, images_root=Path(images_root or ".runtime/images"))
        self._image_edit = ImageEditCore(registry, images_root=Path(images_root or ".runtime/images"))

    def Generate(self, request, context):
        yield from self._engine.generate(request)

    def Prefill(self, request, context):
        return self._engine.prefill(request)

    def Decode(self, request, context):
        yield from self._engine.decode(request)

    def Abort(self, request, context):
        found = self._engine.abort(request.request_id)
        return inference_pb2.AbortResponse(ok=found, found=found)

    def Embed(self, request, context):
        return self._embedding.embed(request)

    def Rerank(self, request, context):
        return self._rerank.rerank(request)

    def Transcribe(self, request, context):
        return self._transcription.transcribe(request)

    def Speak(self, request, context):
        return self._speech.speak(request)

    def ImageGenerate(self, request, context):
        return self._image_generation.generate(request)

    def ImageEdit(self, request, context):
        return self._image_edit.edit(request)


class WorkerMaintenanceService(maintenance_pb2_grpc.MaintenanceServiceServicer):
    def __init__(self, registry: WorkerRegistry, jobs_root: Path | str | None = None) -> None:
        root = Path(jobs_root or ".runtime/model-ops")
        self._core = MaintenanceCore(registry, jobs_root=root)

    def ConvertModel(self, request, context):
        yield from self._core.convert_model(request)

    def GetModelInfo(self, request, context):
        return self._core.get_model_info(request)

    def RunDoctor(self, request, context):
        return self._core.doctor_response(request)

    def RunBench(self, request, context):
        yield from self._core.bench_events(request)


class WorkerCacheService(cache_pb2_grpc.CacheServiceServicer):
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def GetCacheStats(self, request, context):
        return self._registry.cache_stats_response()

    def PinPrefix(self, request, context):
        return cache_pb2.PinPrefixResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Pinning is deferred in phase 0."),
        )

    def UnpinPrefix(self, request, context):
        return cache_pb2.UnpinPrefixResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Unpinning is deferred in phase 0."),
        )

    def SaveBoundarySnapshot(self, request, context):
        return cache_pb2.SaveBoundarySnapshotResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Boundary snapshots are deferred in phase 0."),
        )

    def RestoreBoundarySnapshot(self, request, context):
        return cache_pb2.RestoreBoundarySnapshotResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Boundary restore is deferred in phase 0."),
        )

    def PurgeCache(self, request, context):
        return cache_pb2.PurgeCacheResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Cache purge is deferred in phase 0."),
        )


def build_registry_for_backend(backend_mode: str) -> WorkerRegistry:
    process_memory_budget_bytes = max(0, int(os.environ.get("MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES", "0")))
    memory_headroom_bytes = max(0, int(os.environ.get("MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES", "0")))
    if backend_mode == "deterministic":
        return WorkerRegistry(
            runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
            embedding_runtime=DeterministicEmbeddingRuntime(),
            rerank_runtime=DeterministicRerankRuntime(),
            process_memory_budget_bytes=process_memory_budget_bytes,
            memory_headroom_bytes=memory_headroom_bytes,
        )
    return WorkerRegistry(
        process_memory_budget_bytes=process_memory_budget_bytes,
        memory_headroom_bytes=memory_headroom_bytes,
    )


def build_server(
    socket_path: str,
    registry: WorkerRegistry | None = None,
    backend_mode: str = "auto",
    metrics_exporter: BootstrapMetricsExporter | None = None,
):
    registry_started_at = time.perf_counter_ns()
    registry = registry or build_registry_for_backend(backend_mode)
    if metrics_exporter is not None:
        metrics_exporter.set_milliseconds(
            "python_worker.registry_init_ms",
            _elapsed_milliseconds_since(registry_started_at),
        )

    server_build_started_at = time.perf_counter_ns()
    socket_path = os.fspath(Path(socket_path).resolve())
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    maintenance_service = WorkerMaintenanceService(registry)
    cache_service = WorkerCacheService(registry)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(runtime_service, server)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(inference_service, server)
    maintenance_pb2_grpc.add_MaintenanceServiceServicer_to_server(maintenance_service, server)
    cache_pb2_grpc.add_CacheServiceServicer_to_server(cache_service, server)
    server.add_insecure_port(f"unix://{socket_path}")
    if metrics_exporter is not None:
        metrics_exporter.set_milliseconds(
            "python_worker.server_build_ms",
            _elapsed_milliseconds_since(server_build_started_at),
        )
    return server, runtime_service, inference_service


def main() -> None:
    bootstrap_started_at = time.perf_counter_ns()
    metrics_exporter = BootstrapMetricsExporter(os.environ.get("MELIX_PYTHON_WORKER_METRICS_PATH"))
    metrics_exporter.set_milliseconds(
        "python_worker.spawn_to_bootstrap_ms",
        _elapsed_milliseconds_from_origin(os.environ.get("MELIX_PYTHON_WORKER_STARTUP_T0_NS"), bootstrap_started_at),
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/var/run/melix/worker-text-001.sock")
    parser.add_argument("--backend-mode", choices=["auto", "deterministic"], default="auto")
    args = parser.parse_args()
    metrics_exporter.set_milliseconds(
        "python_worker.arg_parse_ms",
        _elapsed_milliseconds_since(bootstrap_started_at),
    )

    server, _, _ = build_server(
        args.socket_path,
        backend_mode=getattr(args, "backend_mode", "auto"),
        metrics_exporter=metrics_exporter,
    )
    server_start_started_at = time.perf_counter_ns()
    server.start()
    metrics_exporter.set_milliseconds(
        "python_worker.server_start_ms",
        _elapsed_milliseconds_since(server_start_started_at),
    )
    metrics_exporter.set_milliseconds(
        "python_worker.bootstrap_ms",
        _elapsed_milliseconds_since(bootstrap_started_at),
    )
    server.wait_for_termination()


def _elapsed_milliseconds_since(started_at_nanoseconds: int, now_nanoseconds: int | None = None) -> float:
    current = now_nanoseconds if now_nanoseconds is not None else time.perf_counter_ns()
    if current < started_at_nanoseconds:
        return 0.0
    return (current - started_at_nanoseconds) / 1_000_000.0


def _elapsed_milliseconds_from_origin(raw_origin_nanoseconds: str | None, now_nanoseconds: int | None = None) -> float:
    if raw_origin_nanoseconds is None:
        return 0.0
    try:
        origin_nanoseconds = int(raw_origin_nanoseconds)
    except ValueError:
        return 0.0
    if origin_nanoseconds < 0:
        return 0.0
    return _elapsed_milliseconds_since(origin_nanoseconds, now_nanoseconds)
