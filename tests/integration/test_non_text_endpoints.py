from __future__ import annotations

import base64
import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_embeddings_endpoint_returns_vectors() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-embed"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
            data=json.dumps(
                {
                    "model": "melix-dev-embed",
                    "input": ["alpha", "beta"],
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["object"] == "list"
        assert payload["model"] == "melix-dev-embed"
        assert len(payload["data"]) == 2
        assert len(payload["data"][0]["embedding"]) == 8
    finally:
        stack.stop()


def test_rerank_endpoint_returns_ranked_items() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-rerank"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{stack.http_port}/v1/rerank",
            data=json.dumps(
                {
                    "model": "melix-dev-rerank",
                    "query": "swift worker",
                    "documents": ["python bridge", "swift worker"],
                    "top_k": 2,
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["model"] == "melix-dev-rerank"
        assert [item["index"] for item in payload["data"]] == [1, 0]
    finally:
        stack.stop()


def test_health_and_cache_endpoints_return_operator_state() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        with urllib.request.urlopen(f"http://127.0.0.1:{stack.http_port}/health", timeout=10) as response:
            health_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"http://127.0.0.1:{stack.http_port}/v1/cache/stats", timeout=10) as response:
            cache_payload = json.loads(response.read().decode("utf-8"))

        assert health_payload["status"] in {"ok", "degraded"}
        assert health_payload["routes"]["swift_text"] is True
        assert "python_embedding" in health_payload["routes"]
        assert "python_rerank" in health_payload["routes"]
        assert "python_transcription" in health_payload["routes"]
        assert "python_speech" in health_payload["routes"]
        assert cache_payload["l1_bytes"] >= 0
        assert cache_payload["l2_bytes"] >= 0
    finally:
        stack.stop()


def test_audio_transcriptions_endpoint_returns_transcript() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-transcribe"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions",
            data=json.dumps(
                {
                    "model": "melix-dev-transcribe",
                    "audio_base64": base64.b64encode(b"hello audio").decode("ascii"),
                    "format": "wav",
                    "language": "en",
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["model"] == "melix-dev-transcribe"
        assert payload["text"] == "hello audio"
        assert payload["language"] == "en"
        assert payload["duration_seconds"] > 0
    finally:
        stack.stop()


def test_audio_speech_endpoint_returns_audio_bytes() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-speech"])
        request = urllib.request.Request(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/speech",
            data=json.dumps(
                {
                    "model": "melix-dev-speech",
                    "input": "hello speech",
                    "voice": "alloy",
                    "format": "wav",
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
            content_type = response.headers.get("content-type")

        assert response.status == 200
        assert content_type == "audio/wav"
        assert payload == b"VOICE=alloy\nFORMAT=wav\nTEXT=hello speech"
    finally:
        stack.stop()
