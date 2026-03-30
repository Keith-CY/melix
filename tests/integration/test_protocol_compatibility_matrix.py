from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_protocol_compatibility_matrix_covers_stream_families() -> None:
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
                "messages": [{"role": "user", "content": "hello compatibility matrix"}],
            },
            "markers": [
                "\"object\":\"chat.completion.chunk\"",
                "\"content\":\"Echo",
                "\"finish_reason\":\"stop\"",
                "data: [DONE]",
            ],
        },
        {
            "name": "completions",
            "url": stack.completions_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "prompt": "hello compatibility matrix",
            },
            "markers": [
                "\"object\":\"text_completion\"",
                "\"text\":\"Echo",
                "\"finish_reason\":\"stop\"",
                "data: [DONE]",
            ],
        },
        {
            "name": "responses",
            "url": stack.responses_url(),
            "headers": {"content-type": "application/json"},
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "instructions": "Be terse.",
                "input": "hello compatibility matrix",
            },
            "markers": [
                "event: response.output_text.delta",
                "\"type\":\"response.output_text.delta\"",
                "event: response.completed",
                "\"type\":\"response.completed\"",
                "data: [DONE]",
            ],
        },
        {
            "name": "messages",
            "url": stack.messages_url(),
            "headers": {
                "content-type": "application/json",
                "x-api-key": "anthropic-local-key",
            },
            "body": {
                "model": "melix-dev-text",
                "stream": True,
                "system": [{"type": "text", "text": "Be terse."}],
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "hello compatibility matrix"}],
                    }
                ],
            },
            "markers": [
                "event: message.delta",
                "\"type\":\"message.delta\"",
                "event: message.completed",
                "\"type\":\"message.completed\"",
                "data: [DONE]",
            ],
        },
    ]

    try:
        for case in cases:
            response = urllib.request.urlopen(
                urllib.request.Request(
                    case["url"],
                    data=json.dumps(case["body"]).encode("utf-8"),
                    headers=case["headers"],
                    method="POST",
                ),
                timeout=10,
            )
            body = response.read().decode("utf-8")

            assert response.status == 200, case["name"]
            assert "text/event-stream" in response.headers["Content-Type"], case["name"]
            for marker in case["markers"]:
                assert marker in body, f"{case['name']} missing marker {marker}"
    finally:
        stack.stop()
