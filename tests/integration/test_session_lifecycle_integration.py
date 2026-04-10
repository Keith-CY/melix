from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.integration.helpers import (
    LiveMelixStack,
    root_package_swift_command,
    root_package_swift_environment,
)


def test_session_lifecycle_smoke_records_live_pause_sleep_wake_and_restart_metrics() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)

    try:
        stack.start()
        stack.stop_control_plane()

        metrics_path = repo_root / ".runtime" / "phase1" / "metrics" / "m10-session-lifecycle-smoke.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.unlink(missing_ok=True)

        environment = root_package_swift_environment(repo_root, base_env=os.environ.copy())
        environment["MELIX_REPO_ROOT"] = str(repo_root)
        environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = str(stack.swift_socket_path)
        environment["MELIX_WORKER_SOCKET_PATH"] = str(stack.python_socket_path)
        environment["MELIX_CONTROL_PLANE_METRICS_PATH"] = str(metrics_path)

        result = subprocess.run(
            root_package_swift_command(
                repo_root,
                "run",
                ["melix-session-lifecycle-smoke", "--json"],
            ),
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        payload = json.loads(result.stdout)

        assert payload["ok"] is True
        assert payload["serverSessionID"] == "server-session-1"
        assert payload["modelID"] == "melix-dev-text"
        assert payload["scenarios"]["pause"]["lifecycle"] == "paused"
        assert payload["scenarios"]["pause"]["blockedStatus"] == "unavailable"
        assert payload["scenarios"]["idle_sleep"]["lifecycle"] == "sleeping"
        assert payload["scenarios"]["idle_sleep"]["powerState"] == "light_sleep"
        assert payload["scenarios"]["wake"]["lifecycle"] == "ready"
        assert payload["scenarios"]["wake"]["wakeReason"] == "request_activity"
        assert "Echo: wake the server" in payload["scenarios"]["wake"]["assistantText"]
        assert payload["scenarios"]["restart"]["lifecycle"] == "ready"
        assert "Echo: confirm restart recovery" in payload["scenarios"]["restart"]["assistantText"]
        assert payload["metrics"]["lifecycle.pause_ack_ms"] >= 0
        assert payload["metrics"]["lifecycle.idle_to_light_sleep_ms"] >= 1000
        assert payload["metrics"]["lifecycle.wake_to_ready_ms"] >= 0
        assert payload["metrics"]["lifecycle.restart_recovery_ms"] >= 0
        assert payload["metrics"]["control_plane.server_pause_ms"] >= 0
        assert payload["metrics"]["control_plane.server_idle_policy_ms"] >= 0
        assert payload["metrics"]["control_plane.server_start_ms"] >= 0
        assert payload["metrics"]["control_plane.server_stop_ms"] >= 0
        assert metrics_path.exists()
    finally:
        stack.stop()
