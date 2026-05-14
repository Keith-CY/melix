from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, read_metrics_export


def test_shared_access_accepts_known_api_keys_and_rejects_unknown_keys() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={
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
        },
    )
    stack.start()

    try:
        missing_status, missing_payload = _request_json(stack.models_url())
        unknown_status, unknown_payload = _request_json(stack.models_url(), headers={"x-api-key": "sk-unknown"})
        accepted_status, accepted_payload = _request_json(stack.models_url(), headers={"x-api-key": "sk-codex"})
        metrics = _wait_for_metrics(
            stack.control_plane_metrics_path,
            {
                "shared_access.accepted_client_count": 1,
                "shared_access.rejected_request_count": 2,
            },
        )
        values = metrics["values"]

        assert missing_status == 401
        assert missing_payload["error"]["code"] == "missing_api_key"
        assert unknown_status == 401
        assert unknown_payload["error"]["code"] == "invalid_api_key"
        assert accepted_status == 200
        assert any(item["id"] == "melix-dev-text" for item in accepted_payload["data"])
        assert values["gateway.accepted_api_key_count"] == 2
        assert values["shared_access.enabled"] == 1
        assert values["shared_access.ready"] == 1
        assert values["shared_access.accepted_client_count"] >= 1
        assert values["shared_access.rejected_request_count"] >= 2
        assert values["gateway.auth_validation_failures"] >= 2
    finally:
        stack.stop()


def test_shared_access_disabled_rejects_api_keys_but_keeps_local_trust() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "api_keys",
            "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "false",
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
        },
    )
    stack.start()

    try:
        rejected_status, rejected_payload = _request_json(stack.models_url(), headers={"x-api-key": "sk-codex"})
        local_status, local_payload = _request_json(stack.models_url())
        metrics = _wait_for_metrics(
            stack.control_plane_metrics_path,
            {"shared_access.rejected_request_count": 1},
        )
        values = metrics["values"]

        assert rejected_status == 403
        assert rejected_payload["error"]["code"] == "shared_access_disabled"
        assert local_status == 200
        assert any(item["id"] == "melix-dev-text" for item in local_payload["data"])
        assert values["gateway.accepted_api_key_count"] == 2
        assert values["shared_access.enabled"] == 0
        assert values["shared_access.ready"] == 1
        assert values["shared_access.rejected_request_count"] >= 1
        assert values["gateway.auth_validation_failures"] >= 1
    finally:
        stack.stop()


def test_gateway_request_headers_uses_bearer_token_when_configured() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "bearer_token",
            "MELIX_GATEWAY_BEARER_TOKEN": "  sk-bearer  ",
        },
    )

    assert stack._gateway_request_headers() == {"Authorization": "Bearer sk-bearer"}


def test_gateway_request_headers_returns_empty_when_bearer_token_is_missing() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "bearer_token",
            "MELIX_GATEWAY_BEARER_TOKEN": "   ",
        },
    )

    assert stack._gateway_request_headers() == {}


def test_gateway_request_headers_returns_empty_for_missing_or_invalid_shared_key_payloads() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    missing_keys_stack = LiveMelixStack(
        repo_root,
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "api_keys",
            "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
        },
    )
    invalid_json_stack = LiveMelixStack(
        repo_root,
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "api_keys",
            "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
            "MELIX_GATEWAY_API_KEYS_JSON": "{not-json}",
        },
    )
    non_list_stack = LiveMelixStack(
        repo_root,
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "api_keys",
            "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
            "MELIX_GATEWAY_API_KEYS_JSON": json.dumps({"token": "sk-codex"}),
        },
    )

    assert missing_keys_stack._gateway_request_headers() == {}
    assert invalid_json_stack._gateway_request_headers() == {}
    assert non_list_stack._gateway_request_headers() == {}


def test_gateway_request_headers_selects_first_valid_shared_access_api_key() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        start_python_worker=False,
        environment_overrides={
            "MELIX_GATEWAY_AUTH_MODE": "api_keys",
            "MELIX_GATEWAY_SHARED_ACCESS_ENABLED": "true",
            "MELIX_GATEWAY_API_KEYS_JSON": json.dumps(
                [
                    "skip-me",
                    {"token": "   "},
                    {"token": " sk-codex "},
                    {"token": "sk-unused"},
                ]
            ),
        },
    )

    assert stack._gateway_request_headers() == {"x-api-key": "sk-codex"}


def _request_json(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _wait_for_metrics(
    metrics_path: Path,
    expected: dict[str, float],
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if metrics_path.exists():
            payload = read_metrics_export(metrics_path)
            values = payload.get("values", {})
            if isinstance(values, dict) and all(
                float(values.get(key, 0)) >= minimum for key, minimum in expected.items()
            ):
                return payload
        time.sleep(0.1)
    expected_summary = ", ".join(f"{key}>={minimum:g}" for key, minimum in expected.items())
    raise AssertionError(f"timed out waiting for metrics: {expected_summary}")
