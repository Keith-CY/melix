#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack


OPENAI_EXAMPLE_INPUT = "Hello from Melix"
ANTHROPIC_VERSION = "2023-06-01"
SHARED_ACCESS_ENV = {
    "MELIX_GATEWAY_AUTH_MODE": "api_keys",
    "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
    "MELIX_GATEWAY_API_KEYS_JSON": json.dumps(
        [
            {
                "id": "desktop-agent",
                "label": "Desktop Agent",
                "token_hint": "desktop-agent",
                "token": "sk-desktop",
            }
        ],
        sort_keys=True,
    ),
}


def request_json(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def request_sse(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str],
) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def run_smoke(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=SHARED_ACCESS_ENV)
    stack.start()

    try:
        gateway_headers = stack._gateway_request_headers()
        health_status, health_payload = request_json(
            f"http://127.0.0.1:{stack.http_port}/health"
        )
        health_diagnostics_status, health_diagnostics_payload = request_json(
            f"http://127.0.0.1:{stack.http_port}/v1/melix/health",
            headers=gateway_headers,
        )
        responses_status, responses_content_type, responses_body = request_sse(
            stack.responses_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "input": OPENAI_EXAMPLE_INPUT,
            },
            headers={"content-type": "application/json", **gateway_headers},
        )
        messages_status, messages_content_type, messages_body = request_sse(
            stack.messages_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": OPENAI_EXAMPLE_INPUT}],
            },
            headers={
                "content-type": "application/json",
                "anthropic-version": ANTHROPIC_VERSION,
                **gateway_headers,
            },
        )

        if health_status != 200:
            raise AssertionError(f"/health returned {health_status}")
        if health_payload.get("status") != "ok" or "routes" in health_payload:
            raise AssertionError(f"unexpected health status: {health_payload}")
        if health_diagnostics_status != 200:
            raise AssertionError(f"/v1/melix/health returned {health_diagnostics_status}")
        if health_diagnostics_payload.get("status") not in {"ok", "degraded"}:
            raise AssertionError(f"unexpected health diagnostics status: {health_diagnostics_payload}")
        routes = health_diagnostics_payload.get("routes", {})
        if not isinstance(routes, dict) or routes.get("swift_text") is not True:
            raise AssertionError(f"swift_text route is not ready: {health_diagnostics_payload}")

        if responses_status != 200:
            raise AssertionError(f"/v1/responses returned {responses_status}: {responses_body}")
        if "text/event-stream" not in responses_content_type:
            raise AssertionError(f"responses content type is not SSE: {responses_content_type}")
        if "event: response.output_text.delta" not in responses_body:
            raise AssertionError("responses example did not emit output deltas")
        if "event: response.completed" not in responses_body or "data: [DONE]" not in responses_body:
            raise AssertionError("responses example did not complete cleanly")

        if messages_status != 200:
            raise AssertionError(f"/v1/messages returned {messages_status}: {messages_body}")
        if "text/event-stream" not in messages_content_type:
            raise AssertionError(f"messages content type is not SSE: {messages_content_type}")
        if "event: message.delta" not in messages_body:
            raise AssertionError("messages example did not emit message deltas")
        if "event: message.completed" not in messages_body or "data: [DONE]" not in messages_body:
            raise AssertionError("messages example did not complete cleanly")

        return {
            "ok": True,
            "base_url": f"http://127.0.0.1:{stack.http_port}/v1",
            "startup_timings_ms": stack.startup_timings,
            "examples": {
                "model_id": "melix-dev-text",
                "input": OPENAI_EXAMPLE_INPUT,
                "anthropic_version": ANTHROPIC_VERSION,
                "auth_header_names": sorted(gateway_headers.keys()),
            },
            "health": {
                "status_code": health_status,
                "status": health_payload["status"],
            },
            "health_diagnostics": {
                "status_code": health_diagnostics_status,
                "status": health_diagnostics_payload["status"],
                "swift_text_ready": routes["swift_text"],
            },
            "responses": {
                "status_code": responses_status,
                "content_type": responses_content_type,
                "contains_output_delta": "event: response.output_text.delta" in responses_body,
                "contains_completed_event": "event: response.completed" in responses_body,
            },
            "messages": {
                "status_code": messages_status,
                "content_type": messages_content_type,
                "contains_delta_event": "event: message.delta" in messages_body,
                "contains_completed_event": "event: message.completed" in messages_body,
            },
        }
    finally:
        stack.stop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the M13.4 API onboarding quick-start smoke.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root containing the Melix workspaces.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable payload.",
    )
    args = parser.parse_args()

    payload = run_smoke(args.repo_root.resolve())
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M13.4 API onboarding smoke passed.")
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
