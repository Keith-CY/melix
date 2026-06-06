from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    cache_pb2,
    cache_pb2_grpc,
    inference_pb2,
    inference_pb2_grpc,
    maintenance_pb2,
    maintenance_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "handshake",
            "load-model",
            "unload-model",
            "get-runtime-stats",
            "get-cache-stats",
            "generate",
            "prefill",
            "decode",
            "abort",
            "embed",
            "rerank",
            "transcribe",
            "speak",
            "speak-stream",
            "image-generate",
            "image-edit",
            "get-model-info",
            "convert-model",
            "run-doctor",
            "search-hub-models",
            "get-hub-model-card",
            "run-bench",
            "run-bench-matrix",
            "run-evaluation",
            "export-results",
            "export-results-stream",
            "submit-results",
        ],
    )
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--request-b64", required=True)
    args = parser.parse_args()
    socket_path = Path(args.socket_path).resolve()

    request_bytes = base64.b64decode(args.request_b64)

    try:
        with grpc.insecure_channel(f"unix://{socket_path}", options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)]) as channel:
            if args.command == "handshake":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.HandshakeRequest.FromString(request_bytes)
                emit_message(stub.Handshake(request).SerializeToString())
            elif args.command == "load-model":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.LoadModelRequest.FromString(request_bytes)
                emit_message(stub.LoadModel(request).SerializeToString())
            elif args.command == "unload-model":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.UnloadModelRequest.FromString(request_bytes)
                emit_message(stub.UnloadModel(request).SerializeToString())
            elif args.command == "get-runtime-stats":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.GetRuntimeStatsRequest.FromString(request_bytes)
                emit_message(stub.GetRuntimeStats(request).SerializeToString())
            elif args.command == "get-cache-stats":
                stub = cache_pb2_grpc.CacheServiceStub(channel)
                request = cache_pb2.GetCacheStatsRequest.FromString(request_bytes)
                emit_message(stub.GetCacheStats(request).SerializeToString())
            elif args.command == "generate":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.GenerateRequest.FromString(request_bytes)
                for event in stub.Generate(request):
                    emit_message(event.SerializeToString())
            elif args.command == "prefill":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.PrefillRequest.FromString(request_bytes)
                emit_message(stub.Prefill(request).SerializeToString())
            elif args.command == "decode":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.DecodeRequest.FromString(request_bytes)
                for event in stub.Decode(request):
                    emit_message(event.SerializeToString())
            elif args.command == "embed":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.EmbedRequest.FromString(request_bytes)
                emit_message(stub.Embed(request).SerializeToString())
            elif args.command == "rerank":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.RerankRequest.FromString(request_bytes)
                emit_message(stub.Rerank(request).SerializeToString())
            elif args.command == "transcribe":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.TranscribeRequest.FromString(request_bytes)
                emit_message(stub.Transcribe(request).SerializeToString())
            elif args.command == "speak":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.SpeakRequest.FromString(request_bytes)
                emit_message(stub.Speak(request).SerializeToString())
            elif args.command == "speak-stream":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.SpeakRequest.FromString(request_bytes)
                for event in stub.SpeakStream(request):
                    emit_message(event.SerializeToString())
            elif args.command == "image-generate":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.ImageGenerateRequest.FromString(request_bytes)
                emit_message(
                    stub.ImageGenerate(
                        request,
                        timeout=image_request_timeout_seconds(),
                    ).SerializeToString()
                )
            elif args.command == "image-edit":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.ImageEditRequest.FromString(request_bytes)
                emit_message(
                    stub.ImageEdit(
                        request,
                        timeout=image_request_timeout_seconds(),
                    ).SerializeToString()
                )
            elif args.command == "get-model-info":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.GetModelInfoRequest.FromString(request_bytes)
                emit_message(stub.GetModelInfo(request).SerializeToString())
            elif args.command == "convert-model":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.ConvertModelRequest.FromString(request_bytes)
                for event in stub.ConvertModel(request):
                    emit_message(event.SerializeToString())
            elif args.command == "run-doctor":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.RunDoctorRequest.FromString(request_bytes)
                emit_message(stub.RunDoctor(request).SerializeToString())
            elif args.command == "search-hub-models":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.SearchHubModelsRequest.FromString(request_bytes)
                emit_message(stub.SearchHubModels(request).SerializeToString())
            elif args.command == "get-hub-model-card":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.GetHubModelCardRequest.FromString(request_bytes)
                emit_message(stub.GetHubModelCard(request).SerializeToString())
            elif args.command == "run-bench":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.RunBenchRequest.FromString(request_bytes)
                for event in stub.RunBench(request):
                    emit_message(event.SerializeToString())
            elif args.command == "run-bench-matrix":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.RunBenchMatrixRequest.FromString(request_bytes)
                emit_message(stub.RunBenchMatrix(request).SerializeToString())
            elif args.command == "run-evaluation":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.RunEvaluationRequest.FromString(request_bytes)
                emit_message(stub.RunEvaluation(request).SerializeToString())
            elif args.command == "export-results":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.ExportResultsRequest.FromString(request_bytes)
                emit_message(stub.ExportResults(request).SerializeToString())
            elif args.command == "export-results-stream":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.ExportResultsRequest.FromString(request_bytes)
                for event in stub.ExportResultsStream(request):
                    emit_message(event.SerializeToString())
            elif args.command == "submit-results":
                stub = maintenance_pb2_grpc.MaintenanceServiceStub(channel)
                request = maintenance_pb2.SubmitResultsRequest.FromString(request_bytes)
                emit_message(stub.SubmitResults(request).SerializeToString())
            else:
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.AbortRequest.FromString(request_bytes)
                emit_message(stub.Abort(request).SerializeToString())
    except grpc.RpcError as exc:
        emit_error(exc.code().name, exc.details() or "RPC failed")
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover
        emit_error(type(exc).__name__, str(exc))
        raise SystemExit(1) from exc


def emit_message(message: bytes) -> None:
    print(json.dumps({"kind": "message", "message_b64": base64.b64encode(message).decode("ascii")}), flush=True)


def emit_error(code: str, message: str) -> None:
    print(json.dumps({"kind": "error", "code": code, "message": message}), flush=True)


def image_request_timeout_seconds(environment: dict[str, str] | None = None) -> float:
    env = environment or os.environ
    raw_value = env.get("MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS", "").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 0
    if parsed <= 0:
        parsed = 1800
    return float(parsed)


if __name__ == "__main__":
    main()
