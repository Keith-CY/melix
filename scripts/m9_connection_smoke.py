#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
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


def run_smoke(repo_root: Path) -> dict[str, object]:
    keepalive = run_keepalive_scenario(repo_root)
    resumed = run_resume_scenario(repo_root)
    terminal = run_terminal_failure_scenario(repo_root)
    return {
        "ok": True,
        "metrics": {
            "disconnect.keepalive_gap_ms": resumed["metrics"]["disconnect.keepalive_gap_ms"],
            "disconnect.recovery_latency_ms": resumed["metrics"]["disconnect.recovery_latency_ms"],
            "disconnect.resume_success_rate": resumed["metrics"]["disconnect.resume_success_rate"],
            "disconnect.terminal_failure_count": terminal["metrics"]["disconnect.terminal_failure_count"],
        },
        "scenarios": {
            "keepalive": {
                "status": keepalive["status"],
                "request_id": keepalive["request_id"],
                "saw_keepalive": keepalive["saw_keepalive"],
            },
            "resume": {
                "status": resumed["status"],
                "request_id": resumed["request_id"],
                "recovered_request_id": resumed["recovered_request_id"],
            },
            "terminal_failure": {
                "request_id": terminal["request_id"],
                "resume_status": terminal["resume_status"],
                "resume_error_code": terminal["resume_error_code"],
            },
        },
    }


def run_keepalive_scenario(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=RESUME_LIFECYCLE_ENV)
    stack.start()
    try:
        request_id, saw_keepalive, body = stream_full_response(
            stack,
            prompt=" ".join(f"keepalive-token-{index}" for index in range(60)),
        )
        if not saw_keepalive:
            raise RuntimeError("expected keepalive comment before the deterministic stream completed")
        if "data: [DONE]" not in body:
            raise RuntimeError("expected keepalive scenario to terminate with [DONE]")
        return {
            "status": 200,
            "request_id": request_id,
            "saw_keepalive": saw_keepalive,
        }
    finally:
        stack.stop()


def run_resume_scenario(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=RESUME_LIFECYCLE_ENV)
    stack.start()
    try:
        request_id, saw_keepalive, _ = disconnect_after_request_id(
            stack,
            prompt=" ".join(f"resume-token-{index}" for index in range(200)),
        )
        if not request_id or not saw_keepalive:
            raise RuntimeError("failed to capture a resumable request with a keepalive frame")
        time.sleep(0.02)

        recovered_request_id, recovered_body = resume_request(stack, request_id)
        if recovered_request_id != request_id:
            raise RuntimeError("resume path changed the request identity")
        if "data: [DONE]" not in recovered_body:
            raise RuntimeError("resume path did not finish the recovered stream")
        if "stream_disconnect_timeout" in recovered_body:
            raise RuntimeError("resume path replayed a terminal disconnect failure instead of recovering")

        wait_for_metric(
            stack.control_plane_metrics_path,
            "http.stream_disconnect_count",
            minimum=1,
        )
        metrics = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.resume_success_rate",
            minimum=100,
        )["values"]
        metrics = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.keepalive_gap_ms",
            minimum=0.0001,
        )["values"]
        return {
            "status": 200,
            "request_id": request_id,
            "recovered_request_id": recovered_request_id,
            "metrics": metrics,
        }
    finally:
        stack.stop()


def run_terminal_failure_scenario(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=TERMINAL_LIFECYCLE_ENV)
    stack.start()
    try:
        request_id, _, _ = disconnect_after_request_id(
            stack,
            prompt=" ".join(f"terminal-token-{index}" for index in range(220)),
        )
        wait_for_metric(
            stack.control_plane_metrics_path,
            "http.stream_disconnect_count",
            minimum=1,
        )
        metrics = wait_for_metric(
            stack.control_plane_metrics_path,
            "disconnect.terminal_failure_count",
            minimum=1,
        )["values"]
        resume_status, resume_payload = request_json(
            stack.chat_url(),
            method="POST",
            body={
                "model": "melix-dev-text",
                "stream": True,
                "resume_request_id": request_id,
                "messages": [{"role": "user", "content": "attempt a stale resume"}],
            },
        )
        error_code = resume_payload.get("error", {}).get("code")
        if resume_status != 409 or error_code != "request_not_resumable":
            raise RuntimeError("expected terminal failure resume attempt to return request_not_resumable")
        return {
            "request_id": request_id,
            "resume_status": resume_status,
            "resume_error_code": error_code,
            "metrics": metrics,
        }
    finally:
        stack.stop()


def stream_full_response(stack: LiveMelixStack, *, prompt: str) -> tuple[str, bool, str]:
    response = open_stream(stack, prompt=prompt)
    request_id = ""
    saw_keepalive = False
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
    finally:
        response.close()

    return request_id, saw_keepalive, "".join(chunks)


def disconnect_after_request_id(stack: LiveMelixStack, *, prompt: str) -> tuple[str, bool, str]:
    response = open_stream(stack, prompt=prompt)
    request_id = ""
    saw_keepalive = False
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


def resume_request(stack: LiveMelixStack, request_id: str) -> tuple[str, str]:
    response = urllib.request.urlopen(
        urllib.request.Request(
            stack.chat_url(),
            data=json.dumps(
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "resume_request_id": request_id,
                    "messages": [{"role": "user", "content": "resume the active stream"}],
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        ),
        timeout=30,
    )

    recovered_request_id = ""
    chunks: list[str] = []
    try:
        while True:
            line = response.readline().decode("utf-8")
            if not line:
                break
            chunks.append(line)
            if not line.startswith("data: "):
                continue
            body = line.removeprefix("data: ").strip()
            if not body or body == "[DONE]":
                continue
            event = json.loads(body)
            candidate = event.get("id") or event.get("request_id")
            if isinstance(candidate, str) and candidate:
                recovered_request_id = candidate
    finally:
        response.close()

    return recovered_request_id, "".join(chunks)


def open_stream(stack: LiveMelixStack, *, prompt: str):
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": f"session-{uuid.uuid4().hex[:8]}",
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8"),
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
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def wait_for_metric(
    metrics_path: Path,
    key: str,
    *,
    minimum: float,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if metrics_path.exists():
            payload = read_metrics_export(metrics_path)
            values = payload.get("values", {})
            if isinstance(values, dict) and float(values.get(key, 0)) >= minimum:
                return payload
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for metric {key}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9.6 connection lifecycle smoke."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable payload.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root for local stack startup.",
    )
    args = parser.parse_args()

    payload = run_smoke(args.repo_root.resolve())
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M9.6 connection lifecycle smoke passed.")
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
