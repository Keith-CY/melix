from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack


def timed_json_request(url: str, *, payload: dict | None = None) -> tuple[float, dict]:
    data = None
    headers = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
        method = "POST"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started_at = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.loads(response.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    return elapsed_ms, body


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stack = LiveMelixStack(repo_root)
    stack.start()

    try:
        embeddings_inputs = [f"embedding row {index}" for index in range(16)]
        embeddings_ms, embeddings_payload = timed_json_request(
            f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
            payload={"model": "melix-dev-embed", "input": embeddings_inputs},
        )
        embeddings_rows = len(embeddings_payload["data"])
        embeddings_rps = embeddings_rows / max(embeddings_ms / 1000, 0.001)

        rerank_documents = [f"document {index} swift worker routing" for index in range(32)]
        rerank_ms, rerank_payload = timed_json_request(
            f"http://127.0.0.1:{stack.http_port}/v1/rerank",
            payload={
                "model": "melix-dev-rerank",
                "query": "swift worker routing",
                "documents": rerank_documents,
                "top_k": 5,
            },
        )
        rerank_docs_per_second = len(rerank_documents) / max(rerank_ms / 1000, 0.001)

        health_ms, health_payload = timed_json_request(f"http://127.0.0.1:{stack.http_port}/health")
        cache_ms, cache_payload = timed_json_request(f"http://127.0.0.1:{stack.http_port}/v1/cache/stats")

        print(
            "embeddings "
            f"rows={embeddings_rows} latency_ms={embeddings_ms:.2f} items_per_second={embeddings_rps:.2f}"
        )
        print(
            "rerank "
            f"documents={len(rerank_documents)} latency_ms={rerank_ms:.2f} docs_per_second={rerank_docs_per_second:.2f}"
        )
        print(
            "health "
            f"status={health_payload['status']} latency_ms={health_ms:.2f} "
            f"swift_text={health_payload['routes']['swift_text']} "
            f"python_embedding={health_payload['routes']['python_embedding']} "
            f"python_rerank={health_payload['routes']['python_rerank']}"
        )
        print(
            "cache_stats "
            f"latency_ms={cache_ms:.2f} "
            f"l1_bytes={cache_payload['l1_bytes']} "
            f"l2_bytes={cache_payload['l2_bytes']} "
            f"compression_ratio={cache_payload['compression_ratio']}"
        )
        print(
            "rerank_top_results "
            + json.dumps(rerank_payload["data"][:3], sort_keys=True)
        )
    finally:
        stack.stop()


if __name__ == "__main__":
    main()
