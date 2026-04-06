from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def _assert_chat_stream(stack: LiveMelixStack, prompt: str) -> None:
    response = urllib.request.urlopen(
        urllib.request.Request(
            stack.chat_url(),
            data=json.dumps(
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        ),
        timeout=10,
    )
    body = response.read().decode("utf-8")

    assert response.status == 200
    assert "text/event-stream" in response.headers["Content-Type"]
    assert "\"content\":\"Echo" in body
    assert "data: [DONE]" in body


def test_text_generation_endpoint_supports_mistral4_python_compatibility_family_override() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        environment_overrides={
            "MELIX_DEV_TEXT_FAMILY_ID": "mistral4",
            "MELIX_DEV_TEXT_MODEL_PATH": "models/mistral-small-4",
        },
    )
    stack.start()

    try:
        _assert_chat_stream(stack, "hello mistral4")
    finally:
        stack.stop()


def test_text_generation_endpoint_supports_qwen3moe_family_override() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        environment_overrides={
            "MELIX_DEV_TEXT_FAMILY_ID": "qwen3moe",
            "MELIX_DEV_TEXT_MODEL_PATH": "models/qwen3-moe-128e",
        },
    )
    stack.start()

    try:
        _assert_chat_stream(stack, "hello qwen3moe")
    finally:
        stack.stop()


def test_text_generation_endpoint_supports_deepseek_mla_and_nemotron_h_family_overrides() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for family_id, model_path in (
        ("deepseek-mla", "models/deepseek-v3-mla"),
        ("nemotron-h", "models/nemotron-h"),
    ):
        stack = LiveMelixStack(
            repo_root,
            start_swift_text_worker=False,
            environment_overrides={
                "MELIX_DEV_TEXT_FAMILY_ID": family_id,
                "MELIX_DEV_TEXT_MODEL_PATH": model_path,
            },
        )
        stack.start()
        try:
            _assert_chat_stream(stack, f"hello {family_id}")
        finally:
            stack.stop()
