from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_stream_usage_is_opt_in_across_text_endpoints() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    cases = [
        {
            "name": "chat.completions",
            "url": stack.chat_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "usage opt in"}],
            },
            "usage_marker": "\"prompt_tokens\":",
        },
        {
            "name": "completions",
            "url": stack.completions_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "prompt": "usage opt in",
            },
            "usage_marker": "\"prompt_tokens\":",
        },
        {
            "name": "responses",
            "url": stack.responses_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "input": "usage opt in",
            },
            "usage_marker": "\"input_tokens\":",
        },
        {
            "name": "messages",
            "url": stack.messages_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "usage opt in"}],
            },
            "usage_marker": "\"input_tokens\":",
        },
    ]

    try:
        for case in cases:
            body_without_usage = dict(case["body"])
            body_without_usage["stream_options"] = {"include_usage": False}
            response_without_usage = urllib.request.urlopen(
                urllib.request.Request(
                    case["url"],
                    data=json.dumps(body_without_usage).encode("utf-8"),
                    headers=case["headers"],
                    method="POST",
                ),
                timeout=10,
            )
            payload_without_usage = response_without_usage.read().decode("utf-8")

            assert response_without_usage.status == 200, case["name"]
            assert case["usage_marker"] not in payload_without_usage, case["name"]

            body_with_usage = dict(case["body"])
            body_with_usage["stream_options"] = {"include_usage": True}
            response_with_usage = urllib.request.urlopen(
                urllib.request.Request(
                    case["url"],
                    data=json.dumps(body_with_usage).encode("utf-8"),
                    headers=case["headers"],
                    method="POST",
                ),
                timeout=10,
            )
            payload_with_usage = response_with_usage.read().decode("utf-8")

            assert response_with_usage.status == 200, case["name"]
            assert "text/event-stream" in response_with_usage.headers["Content-Type"], case["name"]
            assert case["usage_marker"] in payload_with_usage, case["name"]
            assert "data: [DONE]" in payload_with_usage, case["name"]
    finally:
        stack.stop()
