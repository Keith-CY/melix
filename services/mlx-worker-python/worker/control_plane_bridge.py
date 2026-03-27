from __future__ import annotations

import argparse
import base64
import json

import grpc

from packages.protocol.python.worker.v1 import inference_pb2, inference_pb2_grpc, runtime_pb2, runtime_pb2_grpc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["handshake", "load-model", "generate", "abort"])
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--request-b64", required=True)
    args = parser.parse_args()

    request_bytes = base64.b64decode(args.request_b64)

    try:
        with grpc.insecure_channel(f"unix://{args.socket_path}") as channel:
            if args.command == "handshake":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.HandshakeRequest.FromString(request_bytes)
                emit_message(stub.Handshake(request).SerializeToString())
            elif args.command == "load-model":
                stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
                request = runtime_pb2.LoadModelRequest.FromString(request_bytes)
                emit_message(stub.LoadModel(request).SerializeToString())
            elif args.command == "generate":
                stub = inference_pb2_grpc.InferenceServiceStub(channel)
                request = inference_pb2.GenerateRequest.FromString(request_bytes)
                for event in stub.Generate(request):
                    emit_message(event.SerializeToString())
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


if __name__ == "__main__":
    main()
