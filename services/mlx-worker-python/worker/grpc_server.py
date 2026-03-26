from __future__ import annotations

import argparse
from concurrent import futures

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)

from worker.engine.engine_core import EngineCore
from worker.registry import WorkerRegistry


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
        return inference_pb2.EmbedResponse(
            error=common_pb2.ErrorStatus(code="unimplemented", message="Embed is deferred in phase 0.")
        )

    def Rerank(self, request, context):
        return inference_pb2.RerankResponse(
            error=common_pb2.ErrorStatus(code="unimplemented", message="Rerank is deferred in phase 0.")
        )

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


def build_server(socket_path: str, registry: WorkerRegistry | None = None):
    registry = registry or WorkerRegistry()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    runtime_pb2_grpc.add_RuntimeServiceServicer_to_server(runtime_service, server)
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(inference_service, server)
    server.add_insecure_port(f"unix://{socket_path}")
    return server, runtime_service, inference_service


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", default="/var/run/melix/worker-text-001.sock")
    args = parser.parse_args()

    server, _, _ = build_server(args.socket_path)
    server.start()
    server.wait_for_termination()
