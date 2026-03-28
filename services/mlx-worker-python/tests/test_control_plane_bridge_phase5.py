from __future__ import annotations

import base64
import json
import sys

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2

from worker import control_plane_bridge


class FakeChannel:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeInferenceStub:
    def Embed(self, request):
        return inference_pb2.EmbedResponse(
            embeddings=[
                inference_pb2.Embedding(values=[0.1, 0.2]),
                inference_pb2.Embedding(values=[0.3, 0.4]),
            ]
        )

    def Rerank(self, request):
        return inference_pb2.RerankResponse(
            items=[
                inference_pb2.RerankItem(index=1, score=0.9),
                inference_pb2.RerankItem(index=0, score=0.7),
            ]
        )

    def Transcribe(self, request):
        return inference_pb2.TranscribeResponse(
            text=request.audio_bytes.decode("utf-8"),
            language=request.language or "und",
            duration_seconds=0.25,
        )

    def Speak(self, request):
        return inference_pb2.SpeakResponse(
            audio_bytes=f"VOICE={request.voice or 'default'}\nFORMAT={request.format or 'wav'}\nTEXT={request.input}".encode(
                "utf-8"
            ),
            format=request.format or "wav",
        )


class FakeMaintenanceStub:
    def GetModelInfo(self, request):
        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind="text",
            max_context=8192,
            supported_parsers=["text"],
        )

    def ConvertModel(self, request):
        yield maintenance_pb2.ConvertModelEvent(
            started=maintenance_pb2.ConvertStarted(job_id="job-1")
        )
        yield maintenance_pb2.ConvertModelEvent(
            completed=maintenance_pb2.ConvertCompleted(output_path="/tmp/model-ops/quantize.artifact")
        )


def test_bridge_helper_forwards_phase5_unary_and_streaming_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())
    monkeypatch.setattr(control_plane_bridge.maintenance_pb2_grpc, "MaintenanceServiceStub", lambda channel: FakeMaintenanceStub())

    embed_request = inference_pb2.EmbedRequest(
        id=common_pb2.RequestIdentity(request_id="embed-bridge"),
        model_handle="melix-dev-embed::bridge",
        inputs=["alpha", "beta"],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "embed",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(embed_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    embed_line = json.loads(capsys.readouterr().out.strip())
    embed_payload = inference_pb2.EmbedResponse.FromString(base64.b64decode(embed_line["message_b64"]))
    assert len(embed_payload.embeddings) == 2

    rerank_request = inference_pb2.RerankRequest(
        id=common_pb2.RequestIdentity(request_id="rerank-bridge"),
        model_handle="melix-dev-rerank::bridge",
        query="swift worker",
        documents=["python bridge", "swift worker"],
        top_k=2,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "rerank",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(rerank_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    rerank_line = json.loads(capsys.readouterr().out.strip())
    rerank_payload = inference_pb2.RerankResponse.FromString(base64.b64decode(rerank_line["message_b64"]))
    assert [item.index for item in rerank_payload.items] == [1, 0]

    info_request = maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-text")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "get-model-info",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(info_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    info_line = json.loads(capsys.readouterr().out.strip())
    info_payload = maintenance_pb2.GetModelInfoResponse.FromString(base64.b64decode(info_line["message_b64"]))
    assert info_payload.ok is True
    assert info_payload.model_kind == "text"

    convert_request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        output_dir="/tmp/model-ops",
        ext={"operation": "quantize"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "convert-model",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(convert_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    convert_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    first_payload = maintenance_pb2.ConvertModelEvent.FromString(base64.b64decode(convert_lines[0]["message_b64"]))
    last_payload = maintenance_pb2.ConvertModelEvent.FromString(base64.b64decode(convert_lines[-1]["message_b64"]))
    assert first_payload.started.job_id == "job-1"
    assert last_payload.completed.output_path == "/tmp/model-ops/quantize.artifact"


def test_bridge_helper_forwards_phase6_audio_unary_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())

    transcribe_request = inference_pb2.TranscribeRequest(
        id=common_pb2.RequestIdentity(request_id="transcribe-bridge"),
        model_handle="melix-dev-transcribe::bridge",
        audio_bytes=b"hello audio",
        format="wav",
        language="en",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "transcribe",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(transcribe_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    transcribe_line = json.loads(capsys.readouterr().out.strip())
    transcribe_payload = inference_pb2.TranscribeResponse.FromString(base64.b64decode(transcribe_line["message_b64"]))
    assert transcribe_payload.text == "hello audio"
    assert transcribe_payload.language == "en"
    assert transcribe_payload.duration_seconds == 0.25

    speak_request = inference_pb2.SpeakRequest(
        id=common_pb2.RequestIdentity(request_id="speak-bridge"),
        model_handle="melix-dev-speech::bridge",
        input="hello speech",
        voice="alloy",
        format="wav",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "speak",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(speak_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    speak_line = json.loads(capsys.readouterr().out.strip())
    speak_payload = inference_pb2.SpeakResponse.FromString(base64.b64decode(speak_line["message_b64"]))
    assert speak_payload.audio_bytes == b"VOICE=alloy\nFORMAT=wav\nTEXT=hello speech"
    assert speak_payload.format == "wav"
