from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_chat_returns_worker_unavailable_when_the_swift_worker_stops() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        stack.stop_swift_text_worker()

        request = urllib.request.Request(
            stack.chat_url(),
            data=json.dumps(
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello after swift worker stop"}],
                }
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request, timeout=10)
            raise AssertionError("Expected the control plane to reject the request when the Swift worker is gone.")
        except urllib.error.HTTPError as error:
            payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 503
            assert payload["error"]["code"] == "worker_unavailable"
    finally:
        stack.stop()
