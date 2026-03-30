from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    inference_pb2,
    inference_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)
from tests.integration.helpers import LiveMelixStack, read_metrics_export
from worker.model_registry.catalog import WorkerModelCatalog


def test_runtime_core_keeps_text_embedding_and_rerank_models_warm_concurrently() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()

        text = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "warm the live text route"}],
            },
        )
        assert text["status"] == 200
        assert "data: [DONE]" in text["body"]

        embedding_status, embedding_payload = post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/embeddings",
            {
                "model": "melix-dev-embed",
                "input": ["alpha", "beta"],
            },
        )
        assert embedding_status == 200
        assert embedding_payload["model"] == "melix-dev-embed"

        rerank_status, rerank_payload = post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/rerank",
            {
                "model": "melix-dev-rerank",
                "query": "swift worker",
                "documents": ["python bridge", "swift worker"],
                "top_k": 2,
            },
        )
        assert rerank_status == 200
        assert rerank_payload["model"] == "melix-dev-rerank"

        stack.wait_for_models(["melix-dev-text", "melix-dev-embed", "melix-dev-rerank"], timeout_seconds=30)
        states = model_states(stack.models_url())
        assert states["melix-dev-text"] in {"warm", "pinned"}
        assert states["melix-dev-embed"] in {"warm", "pinned"}
        assert states["melix-dev-rerank"] in {"warm", "pinned"}
    finally:
        stack.stop()


def test_runtime_core_prefill_memory_guard_rejects_live_requests() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={
            "MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES": "16384",
            "MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES": "16384",
        },
    )

    try:
        stack.start()

        response = run_prefill_memory_guard_probe(stack)
        assert response["ok"] is False
        assert response["error_code"] == "prefill_memory_guard_exceeded"

        metrics = wait_for_metric(
            stack.swift_text_worker_metrics_path,
            "swift_text.prefill_memory_guard_rejection_count",
            minimum=1,
        )
        assert metrics["swift_text.prefill_guard_last_budget_bytes"] == 16384
        assert metrics["swift_text.prefill_guard_last_prompt_tokens"] >= 1
        assert metrics["swift_text.prefill_guard_last_required_bytes"] > metrics["swift_text.prefill_guard_last_budget_bytes"]
    finally:
        stack.stop()


def stream_chat_completion(stack: LiveMelixStack, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return {
            "status": response.status,
            "body": response.read().decode("utf-8"),
        }


def post_json(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def model_states(url: str) -> dict[str, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {item["id"]: item["melix_state"] for item in payload["data"]}


def run_prefill_memory_guard_probe(stack: LiveMelixStack) -> dict[str, object]:
    channel = grpc.insecure_channel(f"unix://{stack.swift_socket_path}")
    try:
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        load_response = runtime_stub.LoadModel(
            runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
            timeout=5,
        )
        assert load_response.ok is True
        assert load_response.model_handle

        response = inference_stub.Prefill(
            inference_pb2.PrefillRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="integration-prefill-guard"),
                    model_handle=load_response.model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="alpha")],
                    )
                ],
                return_decode_handle=True,
                prefill_step_size=0,
            ),
            timeout=5,
        )
        return {
            "ok": response.ok,
            "error_code": response.error.code,
            "error_message": response.error.message,
        }
    finally:
        channel.close()


def wait_for_metric(path: Path, key: str, *, minimum: float, timeout_seconds: float = 10.0) -> dict[str, float]:
    deadline = time.time() + timeout_seconds
    last_seen = 0.0

    while time.time() < deadline:
        if path.exists():
            values = read_metrics_export(path).get("values", {})
            candidate = values.get(key, 0)
            if isinstance(candidate, (int, float)):
                last_seen = float(candidate)
                if last_seen >= minimum:
                    return values
        time.sleep(0.2)

    raise AssertionError(f"Metric {key} never reached {minimum} at {path}; last value was {last_seen}.")
