from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import urllib.error

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "m13_api_onboarding_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m13_api_onboarding_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m13_api_onboarding_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m13_api_onboarding_smoke)


def test_main_prints_machine_readable_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m13_api_onboarding_smoke,
        "run_smoke",
        lambda repo_root: {
            "ok": True,
            "base_url": "http://127.0.0.1:12436/v1",
            "examples": {"input": "Hello from Melix"},
            "health": {"status_code": 200},
            "responses": {"contains_completed_event": True},
            "messages": {"contains_completed_event": True},
            "repo_root": str(repo_root),
        },
    )
    monkeypatch.setattr(
        m13_api_onboarding_smoke.sys,
        "argv",
        ["m13_api_onboarding_smoke.py", "--json", "--repo-root", str(tmp_path)],
    )

    assert m13_api_onboarding_smoke.main() == 0
    output = capsys.readouterr().out

    assert '"ok": true' in output
    assert '"Hello from Melix"' in output
    assert str(tmp_path) in output


def test_main_prints_human_readable_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m13_api_onboarding_smoke,
        "run_smoke",
        lambda repo_root: {"ok": True, "repo_root": str(repo_root)},
    )
    monkeypatch.setattr(
        m13_api_onboarding_smoke.sys,
        "argv",
        ["m13_api_onboarding_smoke.py", "--repo-root", str(tmp_path)],
    )

    assert m13_api_onboarding_smoke.main() == 0
    output = capsys.readouterr().out

    assert "M13.4 API onboarding smoke passed." in output
    assert str(tmp_path) in output


def test_request_json_returns_http_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        url="http://127.0.0.1/health",
        code=401,
        msg="unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"error":{"code":"auth_failed"}}'),
    )
    monkeypatch.setattr(m13_api_onboarding_smoke.urllib.request, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error))

    status, payload = m13_api_onboarding_smoke.request_json("http://127.0.0.1/health")

    assert status == 401
    assert payload["error"]["code"] == "auth_failed"


def test_request_sse_returns_http_error_body_and_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        url="http://127.0.0.1/v1/responses",
        code=400,
        msg="bad request",
        hdrs={"Content-Type": "application/json"},
        fp=io.BytesIO(b'{"error":{"code":"stream_required"}}'),
    )
    monkeypatch.setattr(m13_api_onboarding_smoke.urllib.request, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error))

    status, content_type, body = m13_api_onboarding_smoke.request_sse(
        "http://127.0.0.1/v1/responses",
        {"model": "melix-dev-text", "stream": True, "input": "Hello from Melix"},
        headers={"content-type": "application/json"},
    )

    assert status == 400
    assert content_type == "application/json"
    assert json.loads(body)["error"]["code"] == "stream_required"


class _FakeStack:
    def __init__(self) -> None:
        self.http_port = 11_434
        self.startup_timings = {"swift_text_worker_ready_ms": 1.0}
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def _gateway_request_headers(self) -> dict[str, str]:
        return {"x-api-key": "sk-desktop"}

    def responses_url(self) -> str:
        return "http://127.0.0.1:12436/v1/responses"

    def messages_url(self) -> str:
        return "http://127.0.0.1:12436/v1/messages"


@pytest.mark.parametrize(
    ("health_result", "health_diagnostics_result", "responses_result", "messages_result", "message"),
    [
        ((503, {"status": "ok"}), None, None, None, "/health returned 503"),
        ((200, {"status": "offline"}), None, None, None, "unexpected health status"),
        ((200, {"status": "ok", "routes": {"swift_text": True}}), None, None, None, "unexpected health status"),
        ((200, {"status": "ok"}), (503, {"status": "ok", "routes": {"swift_text": True}}), None, None, "/v1/melix/health returned 503"),
        ((200, {"status": "ok"}), (200, {"status": "offline", "routes": {"swift_text": True}}), None, None, "unexpected health diagnostics status"),
        ((200, {"status": "ok"}), (200, {"status": "ok", "routes": {"swift_text": False}}), None, None, "swift_text route is not ready"),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (500, "text/event-stream; charset=utf-8", "error"),
            None,
            "/v1/responses returned 500",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "application/json", "error"),
            None,
            "responses content type is not SSE",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.completed\ndata: [DONE]"),
            None,
            "responses example did not emit output deltas",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.output_text.delta"),
            None,
            "responses example did not complete cleanly",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.output_text.delta\nevent: response.completed\ndata: [DONE]"),
            (500, "text/event-stream; charset=utf-8", "error"),
            "/v1/messages returned 500",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.output_text.delta\nevent: response.completed\ndata: [DONE]"),
            (200, "application/json", "error"),
            "messages content type is not SSE",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.output_text.delta\nevent: response.completed\ndata: [DONE]"),
            (200, "text/event-stream; charset=utf-8", "event: message.completed\ndata: [DONE]"),
            "messages example did not emit message deltas",
        ),
        (
            (200, {"status": "ok"}),
            (200, {"status": "ok", "routes": {"swift_text": True}}),
            (200, "text/event-stream; charset=utf-8", "event: response.output_text.delta\nevent: response.completed\ndata: [DONE]"),
            (200, "text/event-stream; charset=utf-8", "event: message.delta"),
            "messages example did not complete cleanly",
        ),
    ],
)
def test_run_smoke_rejects_invalid_endpoint_states(
    monkeypatch: pytest.MonkeyPatch,
    health_result: tuple[int, dict[str, object]],
    health_diagnostics_result: tuple[int, dict[str, object]] | None,
    responses_result: tuple[int, str, str] | None,
    messages_result: tuple[int, str, str] | None,
    message: str,
) -> None:
    stack = _FakeStack()
    successful_stream = (
        200,
        "text/event-stream; charset=utf-8",
        "event: response.output_text.delta\nevent: response.completed\ndata: [DONE]",
    )
    successful_message_stream = (
        200,
        "text/event-stream; charset=utf-8",
        "event: message.delta\nevent: message.completed\ndata: [DONE]",
    )
    monkeypatch.setattr(
        m13_api_onboarding_smoke,
        "LiveMelixStack",
        lambda repo_root, environment_overrides: stack,
    )
    json_results = iter(
        [
            health_result,
            health_diagnostics_result or (200, {"status": "ok", "routes": {"swift_text": True}}),
        ]
    )
    monkeypatch.setattr(m13_api_onboarding_smoke, "request_json", lambda url, headers=None: next(json_results))

    stream_results = iter(
        [
            responses_result or successful_stream,
            messages_result or successful_message_stream,
        ]
    )
    monkeypatch.setattr(
        m13_api_onboarding_smoke,
        "request_sse",
        lambda url, payload, headers: next(stream_results),
    )

    with pytest.raises(AssertionError, match=message):
        m13_api_onboarding_smoke.run_smoke(Path("/tmp/melix"))

    assert stack.started is True
    assert stack.stopped is True
