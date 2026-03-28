from __future__ import annotations

import json
import threading
import time
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def test_queue_pressure_surfaces_follower_delay_and_scheduler_metrics() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        prompt = "\n".join(
            [
                "phase-two-queue-pressure",
                "{",
                '  "task": "queue-pressure",',
                '  "repeat": ["alpha", "beta", "gamma", "delta"],',
                '  "shape": {"kind": "structured", "lane": "interactive"}',
                "}",
            ]
        )
        results: dict[str, dict[str, float | str]] = {}

        def run(label: str) -> None:
            request = urllib.request.Request(
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
            )
            started_at = time.perf_counter()
            ttft_ms: float | None = None
            body_parts: list[str] = []

            with urllib.request.urlopen(request, timeout=30) as response:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8")
                    body_parts.append(decoded)
                    if decoded.startswith("data: ") and '"content":"' in decoded and ttft_ms is None:
                        ttft_ms = (time.perf_counter() - started_at) * 1000.0
                results[label] = {
                    "ttft_ms": round(ttft_ms or 0.0, 2),
                    "body": "".join(body_parts),
                }

        leader = threading.Thread(target=run, args=("leader",), daemon=True)
        follower = threading.Thread(target=run, args=("follower",), daemon=True)
        leader.start()
        time.sleep(0.05)
        follower.start()
        leader.join(timeout=30)
        follower.join(timeout=30)

        assert not leader.is_alive()
        assert not follower.is_alive()
        assert "data: [DONE]" in results["leader"]["body"]
        assert "data: [DONE]" in results["follower"]["body"]
        assert results["follower"]["ttft_ms"] > results["leader"]["ttft_ms"]

        metrics = json.loads(stack.control_plane_metrics_path.read_text(encoding="utf-8"))
        values = metrics["values"]
        assert values["scheduler.queue_delay_ms"] > 0
        assert values["scheduler.admission_latency_ms"] >= 0
    finally:
        stack.stop()
