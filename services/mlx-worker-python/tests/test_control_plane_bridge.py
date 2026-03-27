from __future__ import annotations

import base64
import json
import sys

import grpc

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker import control_plane_bridge
from worker.model_registry.catalog import WorkerModelCatalog


class FakeChannel:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntimeStub:
    def Handshake(self, request):
        return runtime_pb2.HandshakeResponse(
            protocol_version=request.protocol_version,
            runtime_version="deterministic-text",
        )

    def LoadModel(self, request):
        return runtime_pb2.LoadModelResponse(
            ok=True,
            model_handle=f"{request.model.model_id}::bridge",
        )


class FakeInferenceStub:
    def Generate(self, request):
        yield inference_pb2.ExecuteEvent(
            request_id=request.execution.id.request_id,
            execution_kind="generate",
            seq=1,
            token_delta=inference_pb2.TokenDelta(text="Echo "),
        )
        yield inference_pb2.ExecuteEvent(
            request_id=request.execution.id.request_id,
            execution_kind="generate",
            seq=2,
            completed=inference_pb2.Completed(finish_reason="stop", assistant_text="Echo hello"),
        )

    def Abort(self, request):
        return inference_pb2.AbortResponse(ok=True, found=True)


class FakeRpcError(grpc.RpcError):
    def code(self):
        class Status:
            name = "UNAVAILABLE"

        return Status()

    def details(self):
        return "worker down"


def test_bridge_helper_handles_health_load_and_generate(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.runtime_pb2_grpc, "RuntimeServiceStub", lambda channel: FakeRuntimeStub())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())

    handshake = runtime_pb2.HandshakeRequest(
        protocol_version="melix.worker.v1",
        worker_id="control-plane",
        controlplane_instance_id="cp-1",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "handshake",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(handshake.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    handshake_line = json.loads(capsys.readouterr().out.strip())
    handshake_payload = runtime_pb2.HandshakeResponse.FromString(base64.b64decode(handshake_line["message_b64"]))
    assert handshake_payload.protocol_version == "melix.worker.v1"

    load_request = runtime_pb2.LoadModelRequest(
        model=WorkerModelCatalog.dev_text_model(),
        pin_on_load=True,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "load-model",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(load_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    load_line = json.loads(capsys.readouterr().out.strip())
    load_payload = runtime_pb2.LoadModelResponse.FromString(base64.b64decode(load_line["message_b64"]))
    assert load_payload.ok is True
    assert load_payload.model_handle == "melix-dev-text::bridge"

    generate_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-bridge"),
            model_handle="melix-dev-text::bridge",
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="hello bridge")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
        return_usage=True,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "generate",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(generate_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    generate_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert inference_pb2.ExecuteEvent.FromString(base64.b64decode(generate_lines[0]["message_b64"])).token_delta.text == "Echo "
    assert inference_pb2.ExecuteEvent.FromString(base64.b64decode(generate_lines[-1]["message_b64"])).completed.finish_reason == "stop"


def test_bridge_helper_forwards_abort(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())

    abort_request = inference_pb2.AbortRequest(request_id="req-abort")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "abort",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(abort_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    abort_line = json.loads(capsys.readouterr().out.strip())
    abort_payload = inference_pb2.AbortResponse.FromString(base64.b64decode(abort_line["message_b64"]))
    assert abort_payload.ok is True
    assert abort_payload.found is True


def test_bridge_helper_emits_error_payloads_for_rpc_failures(monkeypatch, capsys) -> None:
    class FailingInferenceStub:
        def Abort(self, request):
            raise FakeRpcError()

    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FailingInferenceStub())

    abort_request = inference_pb2.AbortRequest(request_id="req-abort")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "abort",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(abort_request.SerializeToString()).decode("ascii"),
        ],
    )

    try:
        control_plane_bridge.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover
        raise AssertionError("Expected the helper to exit when the RPC fails.")

    error_line = json.loads(capsys.readouterr().out.strip())
    assert error_line == {"kind": "error", "code": "UNAVAILABLE", "message": "worker down"}
