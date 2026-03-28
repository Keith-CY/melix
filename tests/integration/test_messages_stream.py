from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_messages_endpoint_streams_from_the_live_worker_path() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        response = urllib.request.urlopen(
            urllib.request.Request(
                stack.messages_url(),
                data=json.dumps(
                    {
                        "model": "melix-dev-text",
                        "stream": True,
                        "system": "Be terse.",
                        "messages": [
                            {"role": "user", "content": "hello messages"}
                        ],
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
        assert "event: message.delta" in body
        assert "\"type\":\"message.delta\"" in body
        assert "event: message.completed" in body
        assert "\"type\":\"message.completed\"" in body
        assert "data: [DONE]" in body
    finally:
        stack.stop()
