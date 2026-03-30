from __future__ import annotations

import base64
import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def _post_embeddings(stack: LiveMelixStack, model: str, inputs: list[str]) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
        data=json.dumps({"model": model, "input": inputs}).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload


def _post_rerank(
    stack: LiveMelixStack,
    model: str,
    query: str,
    documents: list[str],
    top_k: int,
) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{stack.http_port}/v1/rerank",
        data=json.dumps(
            {
                "model": model,
                "query": query,
                "documents": documents,
                "top_k": top_k,
            }
        ).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload


def test_embeddings_endpoint_returns_vectors() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-embed"])
        status, payload = _post_embeddings(stack, "melix-dev-embed", ["alpha", "beta"])

        assert status == 200
        assert payload["object"] == "list"
        assert payload["model"] == "melix-dev-embed"
        assert len(payload["data"]) == 2
        assert len(payload["data"][0]["embedding"]) == 8
    finally:
        stack.stop()


def test_embeddings_endpoint_supports_xlmr_backend_override() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bert_stack = LiveMelixStack(repo_root)
    xlmr_stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DEV_EMBED_BACKEND_ID": "xlmr-v1"},
    )

    try:
        bert_stack.start()
        bert_stack.wait_for_models(["melix-dev-embed"])
        bert_status, bert_payload = _post_embeddings(bert_stack, "melix-dev-embed", ["Straße"])
    finally:
        bert_stack.stop()

    try:
        xlmr_stack.start()
        xlmr_stack.wait_for_models(["melix-dev-embed"])
        xlmr_status, xlmr_payload = _post_embeddings(xlmr_stack, "melix-dev-embed", ["Straße"])
    finally:
        xlmr_stack.stop()

    assert bert_status == 200
    assert xlmr_status == 200
    assert bert_payload["model"] == "melix-dev-embed"
    assert xlmr_payload["model"] == "melix-dev-embed"
    assert len(bert_payload["data"][0]["embedding"]) == 8
    assert len(xlmr_payload["data"][0]["embedding"]) == 8
    assert bert_payload["data"][0]["embedding"] != xlmr_payload["data"][0]["embedding"]


def test_embeddings_endpoint_supports_bge_and_mxbai_family_overrides() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    bge_stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DEV_EMBED_FAMILY_ID": "bge-m3"},
    )
    mxbai_stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DEV_EMBED_FAMILY_ID": "mxbai-embed"},
    )

    try:
        bge_stack.start()
        bge_stack.wait_for_models(["melix-dev-embed"])
        bge_status, bge_payload = _post_embeddings(bge_stack, "melix-dev-embed", ["query text"])
    finally:
        bge_stack.stop()

    try:
        mxbai_stack.start()
        mxbai_stack.wait_for_models(["melix-dev-embed"])
        mxbai_status, mxbai_payload = _post_embeddings(mxbai_stack, "melix-dev-embed", ["query text"])
    finally:
        mxbai_stack.stop()

    assert bge_status == 200
    assert mxbai_status == 200
    assert bge_payload["model"] == "melix-dev-embed"
    assert mxbai_payload["model"] == "melix-dev-embed"
    assert len(bge_payload["data"][0]["embedding"]) == 8
    assert len(mxbai_payload["data"][0]["embedding"]) == 10
    assert bge_payload["data"][0]["embedding"] != mxbai_payload["data"][0]["embedding"]


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


def test_rerank_endpoint_prefers_exact_order_for_jina_v3_family() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-rerank"])
        status, payload = _post_rerank(
            stack,
            "melix-dev-rerank",
            "swift runtime",
            ["runtime swift", "swift runtime"],
            2,
        )

        assert status == 200
        assert payload["model"] == "melix-dev-rerank"
        assert [item["index"] for item in payload["data"]] == [1, 0]
        assert payload["data"][0]["score"] > payload["data"][1]["score"]
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
