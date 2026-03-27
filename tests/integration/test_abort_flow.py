from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack, abort_worker_request


def test_abort_finishes_the_live_stream_with_cancelled_completion() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        long_prompt = " ".join(f"token-{index}" for index in range(80))
        response = urllib.request.urlopen(
            urllib.request.Request(
                stack.chat_url(),
                data=json.dumps(
                    {
                        "model": "melix-dev-text",
                        "stream": True,
                        "messages": [{"role": "user", "content": long_prompt}],
                    }
                ).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )

        first_chunk = response.readline().decode("utf-8")
        while first_chunk and not first_chunk.startswith("data: "):
            first_chunk = response.readline().decode("utf-8")

        payload = json.loads(first_chunk.removeprefix("data: ").strip())
        request_id = payload["id"]
        assert abort_worker_request(stack.socket_path, request_id) is True

        body = first_chunk + response.read().decode("utf-8")
        assert "\"finish_reason\":\"cancelled\"" in body
        assert "data: [DONE]" in body
    finally:
        stack.stop()
