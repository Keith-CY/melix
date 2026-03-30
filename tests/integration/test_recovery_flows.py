from __future__ import annotations

import json
import tempfile
import time
import uuid
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, get_cache_stats, read_metrics_export


def test_session_followup_replays_prompt_and_restores_latest_branch_snapshot_through_control_plane() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        source_prompt = "capture a reusable recovery snapshot"
        initial = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "messages": [{"role": "user", "content": source_prompt}],
            },
        )
        assert initial["status"] == 200
        assert initial["request_id"]
        assert "data: [DONE]" in initial["body"]

        cache_response = get_cache_stats(stack.swift_socket_path)
        assert cache_response.snapshot.snapshots

        follow_up = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "parent_request_id": initial["request_id"],
                "messages": [{"role": "user", "content": source_prompt}],
            },
        )
        assert follow_up["status"] == 200
        assert follow_up["request_id"]
        assert "data: [DONE]" in follow_up["body"]

        control_values = wait_for_metric(
            stack.control_plane_metrics_path,
            "session_graph.restore_snapshot_count",
            minimum=1,
        )
        swift_values = wait_for_metric(
            stack.swift_text_worker_metrics_path,
            "swift_text.cache_snapshot_restore_ms",
            minimum=1,
        )

        assert control_values["session_graph.restore_snapshot_count"] >= 1
        assert swift_values["swift_text.cache_snapshot_restore_ms"] >= 1
    finally:
        stack.stop()


def test_boundary_snapshots_restore_after_swift_worker_restart_with_persisted_cache_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="melix-recovery-cache-") as cache_root_str:
        cache_root = Path(cache_root_str)
        source_prompt = "persist a restart-safe boundary snapshot"

        first_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        first_stack.start()
        try:
            initial = stream_chat_completion(
                first_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "messages": [{"role": "user", "content": source_prompt}],
                    "save_boundary_snapshot": True,
                },
            )
            assert initial["status"] == 200
            assert "data: [DONE]" in initial["body"]

            cache_response = get_cache_stats(first_stack.swift_socket_path)
            assert cache_response.snapshot.snapshots
            snapshot_id = cache_response.snapshot.snapshots[-1].snapshot_id
            assert snapshot_id
        finally:
            first_stack.stop()

        second_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        second_stack.start()
        try:
            restored = stream_chat_completion(
                second_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "restore_snapshot_id": snapshot_id,
                    "messages": [{"role": "user", "content": source_prompt}],
                },
            )
            assert restored["status"] == 200
            assert restored["request_id"]
            assert "data: [DONE]" in restored["body"]

            control_values = wait_for_metric(
                second_stack.control_plane_metrics_path,
                "session_graph.restore_snapshot_count",
                minimum=1,
            )
            swift_values = wait_for_metric(
                second_stack.swift_text_worker_metrics_path,
                "swift_text.cache_snapshot_restore_ms",
                minimum=1,
            )

            assert control_values["session_graph.restore_snapshot_count"] >= 1
            assert swift_values["swift_text.cache_snapshot_restore_ms"] >= 1
        finally:
            second_stack.stop()


def test_partial_prefix_followup_walks_back_to_safe_boundary_and_reports_metrics() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        source_prompt = " ".join(f"token{i}" for i in range(1, 25))
        diverged_prompt = " ".join(f"token{i}" for i in range(1, 21)) + " tail-x tail-y"

        initial = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "messages": [{"role": "user", "content": source_prompt}],
            },
        )
        assert initial["status"] == 200
        assert initial["request_id"]

        follow_up = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "parent_request_id": initial["request_id"],
                "messages": [{"role": "user", "content": diverged_prompt}],
            },
        )
        assert follow_up["status"] == 200
        assert follow_up["request_id"]

        control_values = wait_for_metric(
            stack.control_plane_metrics_path,
            "scheduler.partial_restore_walk_back_count",
            minimum=1,
        )
        swift_values = wait_for_metric(
            stack.swift_text_worker_metrics_path,
            "swift_text.partial_restore_walk_back_count",
            minimum=1,
        )

        assert control_values["scheduler.partial_restore_walk_back_count"] >= 1
        assert control_values["scheduler.restore_plan_restored_tokens"] >= 16
        assert control_values["scheduler.restore_plan_total_tokens"] >= 22
        assert swift_values["swift_text.partial_restore_walk_back_count"] >= 1
        assert swift_values["swift_text.partial_restore_restored_tokens"] >= 16
        assert swift_values["swift_text.partial_restore_total_tokens"] >= 22
    finally:
        stack.stop()


def test_warm_followup_prefers_hot_route_and_reduces_ttft_against_cold_baseline() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    stack.start()

    try:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        cold = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "messages": [{"role": "user", "content": "capture a cold baseline before the warm follow-up"}],
            },
        )
        assert cold["status"] == 200
        assert isinstance(cold["ttft_ms"], float)

        warm = stream_chat_completion(
            stack,
            {
                "model": "melix-dev-text",
                "stream": True,
                "session_id": session_id,
                "parent_request_id": cold["request_id"],
                "messages": [{"role": "user", "content": "route this follow-up through the warm path"}],
            },
        )
        assert warm["status"] == 200
        assert isinstance(warm["ttft_ms"], float)
        assert warm["ttft_ms"] < cold["ttft_ms"]

        control_values = wait_for_metric(
            stack.control_plane_metrics_path,
            "session.followup_ttft_delta_ms",
            minimum=1,
        )
        assert control_values["scheduler.prefix_affinity_hit_rate"] >= 100
        assert control_values["scheduler.warm_route_preference_rate"] >= 50
        assert control_values["scheduler.restored_route_rate"] >= 50
        assert control_values["session.followup_ttft_delta_ms"] >= 1
    finally:
        stack.stop()


def stream_chat_completion(stack: LiveMelixStack, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )

    started_at = time.perf_counter()

    with urllib.request.urlopen(request, timeout=30) as response:
        chunks: list[str] = []
        request_id = ""
        ttft_ms: float | None = None

        while True:
            line = response.readline()
            if not line:
                break
            decoded = line.decode("utf-8")
            chunks.append(decoded)

            if not decoded.startswith("data: "):
                continue

            body = decoded.removeprefix("data: ").strip()
            if not body or body == "[DONE]":
                continue

            event = json.loads(body)
            maybe_request_id = event.get("id") or event.get("request_id")
            if isinstance(maybe_request_id, str):
                request_id = maybe_request_id
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            if isinstance(content, str) and content and ttft_ms is None:
                ttft_ms = (time.perf_counter() - started_at) * 1000

        total_ms = (time.perf_counter() - started_at) * 1000
        return {
            "status": response.status,
            "headers": dict(response.headers),
            "request_id": request_id,
            "body": "".join(chunks),
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
        }


def wait_for_metric(path: Path, key: str, *, minimum: float, timeout_seconds: float = 10.0) -> dict[str, float]:
    deadline = time.time() + timeout_seconds
    last_seen = 0.0

    while time.time() < deadline:
        if path.exists():
            values = read_metrics_export(path).get("values", {})
            candidate = values.get(key, 0)
            if isinstance(candidate, (int, float)):
                last_seen = float(candidate)
                if last_seen >= minimum:
                    return values
        time.sleep(0.2)

    raise AssertionError(f"Metric {key} never reached {minimum} at {path}; last value was {last_seen}.")
