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


PERSISTENT_ENV = {
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
    "MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS": "3600",
}


def run_smoke(repo_root: Path) -> dict[str, object]:
    remembered = run_remembered_session_scenario(repo_root)
    ephemeral = run_ephemeral_session_scenario(repo_root)
    return {
        "ok": True,
        "metrics": {
            "persistent_session.active_session_count": remembered["metrics"]["persistent_session.active_session_count"],
            "persistent_session.remembered_session_count": remembered["metrics"][
                "persistent_session.remembered_session_count"
            ],
            "persistent_session.expired_session_count": remembered["metrics"][
                "persistent_session.expired_session_count"
            ],
            "persistent_session.restore_success_rate": remembered["metrics"][
                "persistent_session.restore_success_rate"
            ],
            "persistent_session.sign_out_latency_ms": remembered["metrics"][
                "persistent_session.sign_out_latency_ms"
            ],
        },
        "scenarios": {
            "remembered": {
                "create_status": remembered["create_status"],
                "restored_status": remembered["restored_status"],
                "sign_out_status": remembered["sign_out_status"],
                "revoked_status": remembered["revoked_status"],
                "revoked_code": remembered["revoked_code"],
            },
            "ephemeral": {
                "create_status": ephemeral["create_status"],
                "restored_status": ephemeral["restored_status"],
                "restored_code": ephemeral["restored_code"],
            },
        },
    }


def run_remembered_session_scenario(repo_root: Path) -> dict[str, object]:
    environment = dict(PERSISTENT_ENV)
    environment["MELIX_HOME"] = str(Path("/tmp") / f"melix-persistent-session-smoke-{time.time_ns()}")
    first_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    first_stack.start()

    try:
        create_status, create_payload = request_json(
            f"http://127.0.0.1:{first_stack.http_port}/v1/melix/auth/session",
            method="POST",
            headers={"content-type": "application/json", "x-api-key": "sk-desktop"},
            body={"remember_me": True},
        )
        session_token = str(create_payload["resume"]["token"])
        models_status, _ = request_json(first_stack.models_url(), headers={"X-Melix-Session": session_token})
        if create_status != 200 or models_status != 200:
            raise RuntimeError("failed to create remembered auth session during smoke setup")
    finally:
        first_stack.stop()

    restored_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    restored_stack.start()
    try:
        restored_status, _ = request_json(restored_stack.models_url(), headers={"X-Melix-Session": session_token})
        sign_out_status, _ = request_json(
            f"http://127.0.0.1:{restored_stack.http_port}/v1/melix/auth/session",
            method="DELETE",
            headers={"X-Melix-Session": session_token},
        )
        revoked_status, revoked_payload = request_json(
            restored_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        metrics = wait_for_metric(
            restored_stack.control_plane_metrics_path,
            "persistent_session.sign_out_latency_ms",
            minimum=0,
        )["values"]

        if restored_status != 200:
            raise RuntimeError(f"expected remembered session restore to return 200, got {restored_status}")
        if sign_out_status != 200:
            raise RuntimeError(f"expected remembered session sign-out to return 200, got {sign_out_status}")
        if revoked_status != 401:
            raise RuntimeError(f"expected revoked session access to return 401, got {revoked_status}")

        error = revoked_payload.get("error", {})
        revoked_code = error.get("code")
        session_state = error.get("session_state", {})
        if revoked_code != "revoked_session" or session_state.get("state") != "revoked":
            raise RuntimeError("expected revoked session metadata after sign-out")

        return {
            "create_status": create_status,
            "restored_status": restored_status,
            "sign_out_status": sign_out_status,
            "revoked_status": revoked_status,
            "revoked_code": revoked_code,
            "metrics": metrics,
        }
    finally:
        restored_stack.stop()


def run_ephemeral_session_scenario(repo_root: Path) -> dict[str, object]:
    environment = dict(PERSISTENT_ENV)
    environment["MELIX_HOME"] = str(Path("/tmp") / f"melix-ephemeral-session-smoke-{time.time_ns()}")
    first_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    first_stack.start()

    try:
        create_status, create_payload = request_json(
            f"http://127.0.0.1:{first_stack.http_port}/v1/melix/auth/session",
            method="POST",
            headers={"content-type": "application/json", "x-api-key": "sk-desktop"},
            body={"remember_me": False},
        )
        session_token = str(create_payload["resume"]["token"])
        models_status, _ = request_json(first_stack.models_url(), headers={"X-Melix-Session": session_token})
        if create_status != 200 or models_status != 200:
            raise RuntimeError("failed to create ephemeral auth session during smoke setup")
    finally:
        first_stack.stop()

    restored_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    restored_stack.start()
    try:
        restored_status, restored_payload = request_json(
            restored_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        restored_code = restored_payload.get("error", {}).get("code")
        restored_state = restored_payload.get("error", {}).get("session_state", {}).get("state")
        if restored_status != 401 or restored_code != "missing_session" or restored_state != "missing":
            raise RuntimeError("expected ephemeral auth session to disappear after restart")

        return {
            "create_status": create_status,
            "restored_status": restored_status,
            "restored_code": restored_code,
        }
    finally:
        restored_stack.stop()


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    request_body = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(url, headers=headers or {}, data=request_body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def wait_for_metric(
    metrics_path: Path,
    key: str,
    *,
    minimum: float = 0,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if metrics_path.exists():
            payload = read_metrics_export(metrics_path)
            values = payload.get("values", {})
            if isinstance(values, dict) and float(values.get(key, -1)) >= minimum:
                return payload
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for metric {key}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9.4 persistent-session smoke."
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
        print("M9.4 persistent-session smoke passed.")
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
