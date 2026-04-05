from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tests.integration.helpers import LiveMelixStack


def test_disk_streaming_smoke_records_ram_baseline_and_typed_unsupported_evidence() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stack = LiveMelixStack(repo_root)

    try:
        stack.start()
        stack.stop_control_plane()

        environment = os.environ.copy()
        environment["HOME"] = str(repo_root / ".swift-home")
        environment["CLANG_MODULE_CACHE_PATH"] = str(repo_root / ".build" / "ModuleCache.noindex")
        environment["MELIX_REPO_ROOT"] = str(repo_root)
        environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = str(stack.swift_socket_path)
        environment["MELIX_WORKER_SOCKET_PATH"] = str(stack.python_socket_path)

        result = subprocess.run(
            [
                "swift",
                "run",
                "--package-path",
                str(repo_root),
                "melix-disk-streaming-smoke",
                "--json",
            ],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )
        payload = json.loads(result.stdout)

        assert payload["ok"] is True
        assert payload["modelID"] == "melix-dev-text"

        baseline = payload["baseline"]
        assert baseline["reportPath"]
        assert baseline["metrics"]["bench.smoke.ttft_ms"] >= 0
        assert baseline["metrics"]["bench.smoke.tokens_per_second"] >= 0

        prefer_disk = payload["streamingPreferDisk"]
        assert prefer_disk["requestedMode"] == "prefer_disk"
        assert prefer_disk["effectiveMode"] == "disabled"
        assert prefer_disk["errorCode"] == "disk_streaming_unsupported"
        assert "disk_streaming_unsupported" in prefer_disk["transitionReason"]
        assert prefer_disk["cacheCompatibility"] in {"limited", "disabled"}
        assert prefer_disk["cacheCompatibilityReason"]
        assert "disk" in prefer_disk["cacheCompatibilityReason"].lower()

        require_disk = payload["streamingRequireDisk"]
        assert require_disk["requestedMode"] == "require_disk"
        assert require_disk["effectiveMode"] == "disabled"
        assert require_disk["errorCode"] == "disk_streaming_unsupported"
        assert "disk_streaming_unsupported" in require_disk["transitionReason"]
        assert require_disk["cacheCompatibility"] == "disabled"
        assert require_disk["cacheCompatibilityReason"]
        assert "disk" in require_disk["cacheCompatibilityReason"].lower()

        capability = payload["capability"]
        assert capability["runtimeSupportsDiskStreaming"] is False
        assert capability["cacheCompatibility"] in {"limited", "disabled"}
        assert capability["cacheCompatibilityReason"]
        assert "disk" in capability["cacheCompatibilityReason"].lower()

        future_metrics = payload["futureMetrics"]
        assert future_metrics["ssd_restore_latency_ms"] == "unavailable_until_runtime_support"
        assert future_metrics["disk_streaming_throughput_delta"] == "unavailable_until_runtime_support"
        assert future_metrics["ssd_footprint_bytes"] == "unavailable_until_runtime_support"
    finally:
        stack.stop()
