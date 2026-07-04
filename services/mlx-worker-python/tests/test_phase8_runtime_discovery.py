from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import phase8_runtime_probes


def test_collect_multi_model_coexistence_counts_ready_models_from_capabilities_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root
            self.http_port = 11434

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def models_url(self) -> str:
            return "http://127.0.0.1:11434/v1/models"

        def wait_for_models(self, model_ids: list[str], *, timeout_seconds: float = 120) -> None:
            assert model_ids == ["melix-dev-text", "melix-dev-embed", "melix-dev-rerank"]
            assert timeout_seconds == 30

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]\n\n"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_post_json",
        lambda url, payload: (
            200,
            {"model": payload["model"], "data": [{"index": 0}]},
        ),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_read_model_states",
        lambda url: {
            "melix-dev-text": "warm",
            "melix-dev-embed": "warm",
            "melix-dev-rerank": "pinned",
        },
    )

    report = phase8_runtime_probes._collect_multi_model_coexistence_evidence(tmp_path)

    assert report["multi_model_request_success_rate"] == 100.0
    assert report["multi_model_ready_count"] == 3
    assert report["multi_model_ready_model_ids"] == [
        "melix-dev-text",
        "melix-dev-embed",
        "melix-dev-rerank",
    ]


def test_collect_multi_model_coexistence_requires_ready_discovery_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root
            self.http_port = 11434

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def models_url(self) -> str:
            return "http://127.0.0.1:11434/v1/models"

        def wait_for_models(self, model_ids: list[str], *, timeout_seconds: float = 120) -> None:
            assert model_ids == ["melix-dev-text", "melix-dev-embed", "melix-dev-rerank"]
            assert timeout_seconds == 30

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]\n\n"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_post_json",
        lambda url, payload: (
            200,
            {"model": payload["model"], "data": [{"index": 0}]},
        ),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_read_model_states",
        lambda url: {
            "melix-dev-text": "discovered",
            "melix-dev-embed": "unloaded",
            "melix-dev-rerank": "loading",
        },
    )

    report = phase8_runtime_probes._collect_multi_model_coexistence_evidence(tmp_path)

    assert report["multi_model_request_success_rate"] == 100.0
    assert report["multi_model_ready_count"] == 0
    assert report["multi_model_ready_model_ids"] == []


def test_read_model_states_merges_openai_models_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(url: str, timeout: float) -> FakeResponse:
        requested_urls.append(url)
        if url.endswith("/v1/models"):
            return FakeResponse(
                {
                    "data": [
                        {"id": "melix-dev-text", "melix_state": "warm"},
                    ]
                }
            )
        if url.endswith("/api/capabilities"):
            return FakeResponse(
                {
                    "models": [
                        {"model_id": "melix-dev-embed", "state": "warm"},
                        {"model_id": "melix-dev-rerank", "state": "pinned"},
                    ]
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(
        phase8_runtime_probes.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    assert phase8_runtime_probes._read_model_states("http://127.0.0.1:11434/v1/models") == {
        "melix-dev-text": "warm",
        "melix-dev-embed": "warm",
        "melix-dev-rerank": "pinned",
    }
    assert requested_urls == [
        "http://127.0.0.1:11434/v1/models",
        "http://127.0.0.1:11434/api/capabilities",
    ]


def test_capabilities_url_from_models_url_replaces_openai_models_path() -> None:
    assert (
        phase8_runtime_probes._capabilities_url_from_models_url(
            "http://127.0.0.1:11434/v1/models?ignored=true"
        )
        == "http://127.0.0.1:11434/api/capabilities"
    )
