from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, read_metrics_export


def test_remembered_gateway_sessions_restore_after_restart_and_sign_out_revokes_them() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = Path("/tmp") / f"melix-persistent-session-{time.time_ns()}"
    environment = {
        "MELIX_HOME": str(melix_home),
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

    first_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    first_stack.start()

    try:
        create_status, create_payload = _request_json(
            f"http://127.0.0.1:{first_stack.http_port}/v1/melix/auth/session",
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": "sk-desktop",
            },
            body={"remember_me": True},
        )
        session_token = create_payload["resume"]["token"]
        models_status, _ = _request_json(
            first_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        assert create_status == 200
        assert models_status == 200
    finally:
        first_stack.stop()

    restored_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    restored_stack.start()
    try:
        restored_status, _ = _request_json(
            restored_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        sign_out_status, _ = _request_json(
            f"http://127.0.0.1:{restored_stack.http_port}/v1/melix/auth/session",
            method="DELETE",
            headers={"X-Melix-Session": session_token},
        )
        revoked_status, revoked_payload = _request_json(
            restored_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        metrics = _wait_for_metrics(
            restored_stack.control_plane_metrics_path,
            "persistent_session.sign_out_latency_ms",
            minimum=0,
        )

        assert restored_status == 200
        assert sign_out_status == 200
        assert revoked_status == 401
        assert revoked_payload["error"]["code"] == "revoked_session"
        assert revoked_payload["error"]["session_state"]["state"] == "revoked"
        assert metrics["values"]["persistent_session.active_session_count"] == 0
        assert metrics["values"]["persistent_session.remembered_session_count"] == 0
    finally:
        restored_stack.stop()


def test_non_remembered_gateway_sessions_do_not_restore_after_restart() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = Path("/tmp") / f"melix-ephemeral-session-{time.time_ns()}"
    environment = {
        "MELIX_HOME": str(melix_home),
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

    first_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    first_stack.start()

    try:
        create_status, create_payload = _request_json(
            f"http://127.0.0.1:{first_stack.http_port}/v1/melix/auth/session",
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": "sk-desktop",
            },
            body={"remember_me": False},
        )
        session_token = create_payload["resume"]["token"]
        models_status, _ = _request_json(
            first_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )
        assert create_status == 200
        assert models_status == 200
    finally:
        first_stack.stop()

    restored_stack = LiveMelixStack(repo_root, environment_overrides=environment)
    restored_stack.start()
    try:
        restored_status, restored_payload = _request_json(
            restored_stack.models_url(),
            headers={"X-Melix-Session": session_token},
        )

        assert restored_status == 401
        assert restored_payload["error"]["code"] == "missing_session"
        assert restored_payload["error"]["session_state"]["state"] == "missing"
    finally:
        restored_stack.stop()


def _request_json(
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


def _wait_for_metrics(
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
            if isinstance(values, dict) and float(values.get(key, -1)) >= minimum:
                return payload
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for metric {key}")
