from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, read_metrics_export


BASE_LIFECYCLE_ENV = {
    "MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS": "0.005",
    "MELIX_CONNECTION_RETRY_BACKOFF_SECONDS": "0.01",
    "MELIX_CONNECTION_RETRY_LIMIT": "1",
    "MELIX_CONNECTION_RESUME_BUFFER_LIMIT": "256",
}

RESUME_LIFECYCLE_ENV = {
    **BASE_LIFECYCLE_ENV,
    "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS": "5",
}

TERMINAL_LIFECYCLE_ENV = {
    **BASE_LIFECYCLE_ENV,
    "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS": "0.08",
}


def test_connection_lifecycle_resume_preserves_request_identity_and_records_metrics() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2], environment_overrides=RESUME_LIFECYCLE_ENV)
    stack.start()

    try:
        request_id, saw_keepalive, first_body = disconnect_after_request_id(
            stack,
            prompt=" ".join(f"resume-token-{index}" for index in range(200)),
        )

        assert request_id
        assert saw_keepalive is True
        assert ": keepalive " in first_body

        values = wait_for_metric(
            stack.control_plane_metrics_path,
            "http.stream_disconnect_count",
            minimum=1,
        )
        assert values["http.stream_disconnect_count"] >= 1

        resumed = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "resume_request_id": request_id,
                "messages": [{"role": "user", "content": "resume the active stream"}],
            },
        )

        assert resumed["status"] == 200
        assert resumed["request_id"] == request_id
        assert "data: [DONE]" in resumed["body"]
        assert "stream_disconnect_timeout" not in resumed["body"]

        values = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.resume_success_rate",
            minimum=100,
        )
        assert values["disconnect.recovery_latency_ms"] >= 0
        assert values["disconnect.resume_success_rate"] == 100
        values = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.keepalive_gap_ms",
            minimum=0.0001,
        )
        assert values["disconnect.keepalive_gap_ms"] > 0
    finally:
        stack.stop()


def test_connection_lifecycle_timeout_expires_resume_eligibility_and_surfaces_typed_error() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2], environment_overrides=TERMINAL_LIFECYCLE_ENV)
    stack.start()

    try:
        request_id, _, _ = disconnect_after_request_id(
            stack,
            prompt=" ".join(f"timeout-token-{index}" for index in range(220)),
        )

        wait_for_metric(
            stack.control_plane_metrics_path,
            "http.stream_disconnect_count",
            minimum=1,
        )
        values = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.terminal_failure_count",
            minimum=1,
        )
        assert values["disconnect.resume_success_rate"] == 0

        status, payload = request_json(
            stack.chat_url(),
            method="POST",
            body={
                "model": "melix-dev-text",
                "stream": True,
                "resume_request_id": request_id,
                "messages": [{"role": "user", "content": "attempt a stale resume"}],
            },
        )

        assert status == 409
        assert payload["error"]["code"] == "request_not_resumable"
    finally:
        stack.stop()


def disconnect_after_request_id(stack: LiveMelixStack, *, prompt: str) -> tuple[str, bool, str]:
    response = open_stream(
        stack,
        {
            "model": "melix-dev-text",
            "stream": True,
            "session_id": f"session-{uuid.uuid4().hex[:8]}",
            "messages": [{"role": "user", "content": prompt}],
        },
    )

    saw_keepalive = False
    request_id = ""
    chunks: list[str] = []

    try:
        while True:
            line = response.readline().decode("utf-8")
            if not line:
                break
            chunks.append(line)
            if line.startswith(": keepalive "):
                saw_keepalive = True
                continue
            if not line.startswith("data: "):
                continue

            body = line.removeprefix("data: ").strip()
            if not body or body == "[DONE]":
                continue

            event = json.loads(body)
            candidate = event.get("id") or event.get("request_id")
            if isinstance(candidate, str) and candidate:
                request_id = candidate
                break
    finally:
        response.close()

    return request_id, saw_keepalive, "".join(chunks)


def stream_chat_completion(stack: LiveMelixStack, payload: dict[str, object]) -> dict[str, object]:
    response = open_stream(stack, payload)

    started_at = time.perf_counter()
    chunks: list[str] = []
    request_id = ""

    try:
        while True:
            line = response.readline()
            if not line:
                break
            decoded = line.decode("utf-8")
            chunks.append(decoded)
            if not decoded.startswith("data: "):
                continue
            body = decoded.removeprefix("data: ").strip()
            if not body or body == "[DONE]":
                continue
            event = json.loads(body)
            candidate = event.get("id") or event.get("request_id")
            if isinstance(candidate, str) and candidate:
                request_id = candidate
    finally:
        response.close()

    return {
        "status": 200,
        "request_id": request_id,
        "body": "".join(chunks),
        "total_ms": (time.perf_counter() - started_at) * 1000,
    }


def open_stream(stack: LiveMelixStack, payload: dict[str, object]):
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=30)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        headers={"content-type": "application/json"},
        data=data,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


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
        time.sleep(0.1)

    raise AssertionError(f"Metric {key} never reached {minimum} at {path}; last value was {last_seen}.")
