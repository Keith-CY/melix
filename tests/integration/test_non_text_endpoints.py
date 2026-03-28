from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_embeddings_endpoint_returns_vectors() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
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
    stack.start()

    try:
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
    stack.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{stack.http_port}/health", timeout=10) as response:
            health_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"http://127.0.0.1:{stack.http_port}/v1/cache/stats", timeout=10) as response:
            cache_payload = json.loads(response.read().decode("utf-8"))

        assert health_payload["status"] in {"ok", "degraded"}
        assert health_payload["routes"]["swift_text"] is True
        assert "python_embedding" in health_payload["routes"]
        assert "python_rerank" in health_payload["routes"]
        assert cache_payload["l1_bytes"] >= 0
        assert cache_payload["l2_bytes"] >= 0
    finally:
        stack.stop()
