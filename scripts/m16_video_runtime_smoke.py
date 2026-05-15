#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tests.integration.helpers import LiveMelixStack, read_metrics_export
from worker.productization.acceptance_metrics import build_phase16_video_metrics_report


def _post_json(url: str, payload: dict[str, object], *, timeout: float = 15.0) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read()
            if "application/json" in content_type:
                return response.status, json.loads(body.decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("content-type", "")
        body = exc.read()
        if "application/json" in content_type:
            return exc.code, json.loads(body.decode("utf-8"))
        return exc.code, body


def _timed_post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout: float = 15.0,
) -> tuple[int, object, float]:
    deadline = time.time() + timeout
    last_status = 0
    last_body: object = b""

    while time.time() < deadline:
        started_at = time.perf_counter()
        status, body = _post_json(url, payload, timeout=min(timeout, 10.0))
        elapsed_ms = (time.perf_counter() - started_at) * 1_000.0
        if status not in {409, 503}:
            return status, body, elapsed_ms
        last_status = status
        last_body = body
        time.sleep(0.2)

    return last_status, last_body, timeout * 1_000.0


def _metric_value(snapshot: dict[str, object], key: str) -> float:
    values = snapshot.get("values", {})
    if not isinstance(values, dict):
        return 0.0
    value = values.get(key, 0.0)
    if not isinstance(value, (int, float)):
        return 0.0
    return round(float(value), 2)


def _video_chat_payload(
    *,
    reference: str | None = None,
    inline_bytes: bytes | None = None,
    filename: str,
    prompt: str,
    frame_budget: int,
    start_ms: int = 0,
    end_ms: int = 0,
) -> dict[str, object]:
    input_video: dict[str, object] = {
        "format": "mp4",
        "filename": filename,
        "frame_budget": frame_budget,
    }
    if start_ms > 0:
        input_video["start_ms"] = start_ms
    if end_ms > 0:
        input_video["end_ms"] = end_ms
    if inline_bytes is not None:
        input_video["data"] = base64.b64encode(inline_bytes).decode("ascii")
    elif reference is not None:
        input_video["url"] = reference
    else:
        raise ValueError("expected either reference or inline_bytes")

    return {
        "model": "melix-dev-vlm",
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_video", "input_video": input_video},
                ],
            }
        ],
    }


def _capture_video_scenario(
    stack: LiveMelixStack,
    *,
    scenario_id: str,
    payload: dict[str, object],
    expected_fragments: list[str],
    source_reference: str,
    expected_status: int = 200,
) -> dict[str, Any]:
    status, body, elapsed_ms = _timed_post_json(stack.chat_url(), payload)
    response_text = body.decode("utf-8") if isinstance(body, bytes) else json.dumps(body)
    metrics_snapshot = read_metrics_export(stack.control_plane_metrics_path)

    return {
        "scenario_id": scenario_id,
        "success": status == expected_status
        and all(fragment in response_text for fragment in expected_fragments),
        "request_latency_ms": round(elapsed_ms, 2),
        "source_reference": source_reference,
        "response_excerpt": response_text[:600],
        "video_first_token_ms": _metric_value(metrics_snapshot, "vision.video_first_token_ms"),
        "preprocess_latency_ms": _metric_value(metrics_snapshot, "vision.preprocess_latency_ms"),
        "video_frame_count": _metric_value(metrics_snapshot, "vision.video_frame_count"),
        "video_frame_budget": _metric_value(metrics_snapshot, "vision.video_frame_budget"),
        "video_window_ms": _metric_value(metrics_snapshot, "vision.video_window_ms"),
        "temp_media_artifact_count": _metric_value(
            metrics_snapshot, "vision.temp_media_artifact_count"
        ),
        "temp_media_artifact_bytes": _metric_value(
            metrics_snapshot, "vision.temp_media_artifact_bytes"
        ),
        "temp_media_cleanup_latency_ms": _metric_value(
            metrics_snapshot, "vision.temp_media_cleanup_latency_ms"
        ),
        "temp_media_cleanup_failure_count": _metric_value(
            metrics_snapshot, "vision.temp_media_cleanup_failure_count"
        ),
    }


def _capture_routing_scenario(stack: LiveMelixStack) -> dict[str, Any]:
    video_result: dict[str, Any] = {}

    def run_video_load() -> None:
        status, body, elapsed_ms = _timed_post_json(
            stack.chat_url(),
            _video_chat_payload(
                inline_bytes=b"routing smoke video",
                filename="routing-smoke.mp4",
                prompt="Summarize the clip under load.",
                frame_budget=8,
                start_ms=500,
                end_ms=3_500,
            ),
            timeout=20.0,
        )
        video_result["status"] = status
        video_result["body"] = body.decode("utf-8") if isinstance(body, bytes) else json.dumps(body)
        video_result["latency_ms"] = round(elapsed_ms, 2)

    worker = threading.Thread(target=run_video_load, daemon=True)
    worker.start()
    time.sleep(0.05)

    text_status, text_body, text_elapsed_ms = _timed_post_json(
        stack.chat_url(),
        {
            "model": "melix-dev-text",
            "stream": True,
            "messages": [{"role": "user", "content": "measure text under video load"}],
        },
    )
    worker.join(timeout=20)
    if worker.is_alive():
        raise RuntimeError("video load did not finish during routing smoke")

    metrics_snapshot = read_metrics_export(stack.control_plane_metrics_path)
    text_response = text_body.decode("utf-8") if isinstance(text_body, bytes) else json.dumps(text_body)
    video_response = str(video_result["body"])

    return {
        "text_protection_success": text_status == 200
        and "Echo: measure text under video load" in text_response
        and video_result["status"] == 200
        and "Video content: routing-smoke.mp4" in video_response,
        "video_request_latency_ms": video_result["latency_ms"],
        "text_request_latency_ms": round(text_elapsed_ms, 2),
        "scheduler_text_ttft_under_multimodal_ms": _metric_value(
            metrics_snapshot, "scheduler.text_ttft_under_multimodal_ms"
        ),
        "scheduler_multimodal_queue_delay_ms": _metric_value(
            metrics_snapshot, "scheduler.multimodal_queue_delay_ms"
        ),
        "text_response_excerpt": text_response[:600],
        "video_response_excerpt": video_response[:600],
    }


def run_smoke(repo_root: Path) -> dict[str, Any]:
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DETERMINISTIC_VLM_DELAY_MS": "150"},
    )

    try:
        stack.start()

        local_video_path = stack.runtime_state_root / "fixtures" / "local-smoke.mp4"
        local_video_path.parent.mkdir(parents=True, exist_ok=True)
        local_video_path.write_bytes(b"local video smoke fixture")

        local_path = _capture_video_scenario(
            stack,
            scenario_id="local_path",
            payload=_video_chat_payload(
                reference=str(local_video_path),
                filename="local-smoke.mp4",
                prompt="Summarize the local clip.",
                frame_budget=3,
            ),
            expected_fragments=[
                "Video content: local-smoke.mp4",
                "Frame policy: uniform_sample 3 frame(s)",
                "Prompt: Summarize the local clip.",
            ],
            source_reference=str(local_video_path),
        )

        blocked_remote_url = _capture_video_scenario(
            stack,
            scenario_id="blocked_remote_url",
            payload=_video_chat_payload(
                reference="http://127.0.0.1/remote-video.mp4",
                filename="remote-video.mp4",
                prompt="Summarize the remote clip.",
                frame_budget=4,
            ),
            expected_fragments=[
                "invalid_argument",
                "Unsupported video URI scheme: http.",
            ],
            source_reference="http://127.0.0.1/remote-video.mp4",
            expected_status=400,
        )

        bounded_window = _capture_video_scenario(
            stack,
            scenario_id="bounded_window",
            payload=_video_chat_payload(
                inline_bytes=b"bounded video smoke fixture",
                filename="bounded-window.mp4",
                prompt="Summarize the bounded clip.",
                frame_budget=6,
                start_ms=1_000,
                end_ms=5_000,
            ),
            expected_fragments=[
                "Video content: bounded-window.mp4",
                "Frame policy: uniform_sample 6 frame(s) from 1000ms to 5000ms",
                "Prompt: Summarize the bounded clip.",
            ],
            source_reference="inline_bytes:bounded-window.mp4",
        )

        routing = _capture_routing_scenario(stack)
        report = build_phase16_video_metrics_report(
            local_path=local_path,
            remote_url=blocked_remote_url,
            bounded_window=bounded_window,
            routing=routing,
        )

        return {
            "ok": True,
            "repo_root": str(repo_root),
            "checks": report["checks"],
            "metrics": report["metrics"],
            "scenarios": {
                "local_path": local_path,
                "blocked_remote_url": blocked_remote_url,
                "bounded_window": bounded_window,
                "routing": routing,
            },
        }
    finally:
        stack.stop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the repository-owned M16.4 video runtime smoke."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable payload.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Override the repository root for smoke execution.",
    )
    args = parser.parse_args()

    payload = run_smoke(args.repo_root)
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("M16.4 video runtime smoke passed.")
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
