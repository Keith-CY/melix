#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, read_metrics_export


ENABLED_ENV = {
    "MELIX_GATEWAY_AUTH_MODE": "api_keys",
    "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
    "MELIX_GATEWAY_API_KEYS_JSON": json.dumps(
        [
            {
                "id": "desktop-agent",
                "label": "Desktop Agent",
                "token_hint": "desktop-agent",
                "token": "sk-desktop",
            },
            {
                "id": "codex",
                "label": "Codex",
                "token_hint": "codex",
                "token": "sk-codex",
            },
        ],
        sort_keys=True,
    ),
}

DISABLED_ENV = {
    **ENABLED_ENV,
    "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "false",
}


def run_enabled_scenario(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=ENABLED_ENV)
    stack.start()
    try:
        missing_status, missing_payload = request_json(stack.models_url())
        unknown_status, unknown_payload = request_json(stack.models_url(), headers={"x-api-key": "sk-unknown"})
        x_api_key_status, x_api_key_payload = request_json(stack.models_url(), headers={"x-api-key": "sk-codex"})
        bearer_status, bearer_payload = request_json(
            stack.models_url(),
            headers={"Authorization": "Bearer sk-codex"},
        )
        metrics = wait_for_metrics(stack.control_plane_metrics_path, "shared_access.accepted_client_count", minimum=2)

        return {
            "missing_status": missing_status,
            "missing_code": missing_payload["error"]["code"],
            "unknown_status": unknown_status,
            "unknown_code": unknown_payload["error"]["code"],
            "x_api_key_status": x_api_key_status,
            "x_api_key_contains_text_model": contains_model(x_api_key_payload, "melix-dev-text"),
            "bearer_status": bearer_status,
            "bearer_contains_text_model": contains_model(bearer_payload, "melix-dev-text"),
            "metrics": metrics["values"],
        }
    finally:
        stack.stop()


def run_disabled_scenario(repo_root: Path) -> dict[str, object]:
    stack = LiveMelixStack(repo_root, environment_overrides=DISABLED_ENV)
    stack.start()
    try:
        rejected_status, rejected_payload = request_json(stack.models_url(), headers={"x-api-key": "sk-codex"})
        local_status, local_payload = request_json(stack.models_url())
        metrics = wait_for_metrics(stack.control_plane_metrics_path, "shared_access.rejected_request_count", minimum=1)

        return {
            "rejected_status": rejected_status,
            "rejected_code": rejected_payload["error"]["code"],
            "local_status": local_status,
            "local_contains_text_model": contains_model(local_payload, "melix-dev-text"),
            "metrics": metrics["values"],
        }
    finally:
        stack.stop()


def request_json(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def contains_model(payload: dict[str, object], model_id: str) -> bool:
    data = payload.get("data", [])
    if not isinstance(data, list):
        return False
    return any(isinstance(item, dict) and item.get("id") == model_id for item in data)


def wait_for_metrics(
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
    raise AssertionError(f"timed out waiting for metric {key}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9.3 shared-access smoke."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable payload.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    enabled = run_enabled_scenario(repo_root)
    disabled = run_disabled_scenario(repo_root)

    payload = {
        "ok": True,
        "metrics": {
            "gateway.auth_validation_failures": enabled["metrics"]["gateway.auth_validation_failures"],
            "gateway.accepted_api_key_count": enabled["metrics"]["gateway.accepted_api_key_count"],
            "shared_access.accepted_client_count": enabled["metrics"]["shared_access.accepted_client_count"],
            "shared_access.rejected_request_count": enabled["metrics"]["shared_access.rejected_request_count"],
        },
        "scenarios": {
            "enabled": {
                "missing_status": enabled["missing_status"],
                "missing_code": enabled["missing_code"],
                "unknown_status": enabled["unknown_status"],
                "unknown_code": enabled["unknown_code"],
                "x_api_key_status": enabled["x_api_key_status"],
                "x_api_key_contains_text_model": enabled["x_api_key_contains_text_model"],
                "bearer_status": enabled["bearer_status"],
                "bearer_contains_text_model": enabled["bearer_contains_text_model"],
            },
            "configured_disabled": {
                "rejected_status": disabled["rejected_status"],
                "rejected_code": disabled["rejected_code"],
                "local_status": disabled["local_status"],
                "local_contains_text_model": disabled["local_contains_text_model"],
            },
        },
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M9.3 shared-access smoke passed.")
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
