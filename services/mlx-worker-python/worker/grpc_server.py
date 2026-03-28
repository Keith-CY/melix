from __future__ import annotations

import argparse
import os
from concurrent import futures
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    maintenance_pb2,
    maintenance_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)

from worker.engine.embedding_core import EmbeddingCore
from worker.engine.engine_core import EngineCore
from worker.engine.maintenance_core import MaintenanceCore
from worker.engine.rerank_core import RerankCore
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime


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
            loaded = self._registry.load_model(request.model)
        except Exception as exc:
            return runtime_pb2.LoadModelResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="load_failed", message=str(exc)),
            )

        return runtime_pb2.LoadModelResponse(
            ok=True,
            model_handle=loaded.handle,
            estimated_resident_bytes=loaded.estimated_resident_bytes,
            resolved_capabilities=self._registry.capabilities(),
        )

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
            model_handles=self._registry.list_loaded_models()
        )

    def Drain(self, request, context):
        self._registry.set_draining(request.stop_accepting_new)
        return runtime_pb2.DrainResponse(ok=True)

    def Shutdown(self, request, context):
        return runtime_pb2.ShutdownResponse(ok=True)


class WorkerInferenceService(inference_pb2_grpc.InferenceServiceServicer):
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry
        self._engine = EngineCore(registry)
        self._embedding = EmbeddingCore(registry)
        self._rerank = RerankCore(registry)

    def Generate(self, request, context):
        yield from self._engine.generate(request)

    def Prefill(self, request, context):
        return inference_pb2.PrefillResponse(
            ok=False,
            error=common_pb2.ErrorStatus(code="unimplemented", message="Prefill is deferred in phase 0."),
        )

    def Decode(self, request, context):
        yield inference_pb2.ExecuteEvent(
            request_id=request.execution.id.request_id,
            execution_kind="decode",
            seq=1,
            error=inference_pb2.ErrorEvent(
                error=common_pb2.ErrorStatus(code="unimplemented", message="Decode is deferred in phase 0.")
            ),
        )

    def Abort(self, request, context):
        found = self._engine.abort(request.request_id)
        return inference_pb2.AbortResponse(ok=found, found=found)

    def Embed(self, request, context):
        return self._embedding.embed(request)

    def Rerank(self, request, context):
        return self._rerank.rerank(request)

    def Transcribe(self, request, context):
        return inference_pb2.TranscribeResponse(
            error=common_pb2.ErrorStatus(code="unimplemented", message="Transcribe is deferred in phase 0.")
        )

    def ImageGenerate(self, request, context):
        return inference_pb2.ImageGenerateResponse(
            error=common_pb2.ErrorStatus(code="unimplemented", message="Image generation is deferred in phase 0.")
        )

    def ImageEdit(self, request, context):
        return inference_pb2.ImageEditResponse(
            error=common_pb2.ErrorStatus(code="unimplemented", message="Image edit is deferred in phase 0.")
        )


class WorkerMaintenanceService(maintenance_pb2_grpc.MaintenanceServiceServicer):
    def __init__(self, registry: WorkerRegistry, jobs_root: Path | str | None = None) -> None:
        root = Path(jobs_root or ".runtime/model-ops")
        self._core = MaintenanceCore(registry, jobs_root=root)

    def ConvertModel(self, request, context):
        yield from self._core.convert_model(request)

    def GetModelInfo(self, request, context):
        return self._core.get_model_info(request)

    def RunDoctor(self, request, context):
        return self._core.doctor_response()

    def RunBench(self, request, context):
        yield from self._core.bench_events()


def build_registry_for_backend(backend_mode: str) -> WorkerRegistry:
    if backend_mode == "deterministic":
        return WorkerRegistry(
            runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
            embedding_runtime=DeterministicEmbeddingRuntime(),
            rerank_runtime=DeterministicRerankRuntime(),
        )
    return WorkerRegistry()


def build_server(
    socket_path: str,
    registry: WorkerRegistry | None = None,
    backend_mode: str = "auto",
):
    registry = registry or build_registry_for_backend(backend_mode)
    socket_path = os.fspath(Path(socket_path).resolve())
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    maintenance_service = WorkerMaintenanceService(registry)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(runtime_service, server)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(inference_service, server)
    maintenance_pb2_grpc.add_MaintenanceServiceServicer_to_server(maintenance_service, server)
    server.add_insecure_port(f"unix://{socket_path}")
    return server, runtime_service, inference_service


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/var/run/melix/worker-text-001.sock")
    parser.add_argument("--backend-mode", choices=["auto", "deterministic"], default="auto")
    args = parser.parse_args()

    server, _, _ = build_server(args.socket_path, backend_mode=getattr(args, "backend_mode", "auto"))
    server.start()
    server.wait_for_termination()
