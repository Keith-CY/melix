#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from tests.integration.helpers import LiveMelixStack, get_cache_stats
from worker.productization.release_gates import (
    build_release_gate_report,
    load_release_gate_policy,
)


def collect_restart_recovery_evidence(repo_root: Path) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="melix-phase8-recovery-") as cache_root_str:
        cache_root = Path(cache_root_str)

        first_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        snapshot_id = ""
        try:
            first_stack.start()
            initial = stream_chat_completion(
                first_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "messages": [{"role": "user", "content": "persist a release-gate recovery snapshot"}],
                    "save_boundary_snapshot": True,
                },
            )
            if initial["status"] != 200:
                raise SystemExit(f"initial recovery smoke failed: {initial}")
            cache_response = get_cache_stats(first_stack.swift_socket_path)
            snapshot_id = cache_response.snapshot.snapshots[-1].snapshot_id
            if not snapshot_id:
                raise SystemExit("recovery smoke did not produce a boundary snapshot")
        finally:
            first_stack.stop()

        second_stack = LiveMelixStack(repo_root, swift_cache_root=cache_root)
        started_at = time.perf_counter()
        try:
            second_stack.start()
            restored = stream_chat_completion(
                second_stack,
                {
                    "model": "melix-dev-text",
                    "stream": True,
                    "restore_snapshot_id": snapshot_id,
                    "messages": [{"role": "user", "content": "resume after release-gate restart"}],
                },
            )
            recovery_ms = (time.perf_counter() - started_at) * 1_000.0
            success = restored["status"] == 200 and "data: [DONE]" in restored["body"]
            return {
                "restart_recovery_ms": round(recovery_ms, 2),
                "restart_recovery_success_rate": 100.0 if success else 0.0,
            }
        finally:
            second_stack.stop()


def stream_chat_completion(stack: LiveMelixStack, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        stack.chat_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return {
            "status": response.status,
            "body": body,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--policy",
        default=str(ROOT / "infra/release/phase8-release-gate-policy.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    policy = load_release_gate_policy(args.policy)
    recovery = collect_restart_recovery_evidence(repo_root)
    report = build_release_gate_report(repo_root, policy=policy, recovery=recovery)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
