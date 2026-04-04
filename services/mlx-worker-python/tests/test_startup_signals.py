from __future__ import annotations

import json
import socket
from pathlib import Path

from worker.productization.startup_signals import (
    check_for_updates,
    classify_startup_failure,
    compare_versions,
    normalized_version_parts,
    port_is_available,
    resolve_http_port,
)


def test_check_for_updates_reports_newer_available_version(tmp_path: Path) -> None:
    channel_path = tmp_path / "stable.json"
    channel_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.update_channel.v1",
                "channel": "stable",
                "latest_version": "0.2.0",
            }
        ),
        encoding="utf-8",
    )

    result = check_for_updates("0.1.0", channel_path)

    assert result.checked is True
    assert result.update_available is True
    assert result.latest_version == "0.2.0"
    assert result.summary == "Update available: 0.2.0"


def test_compare_versions_ignores_build_metadata_suffix() -> None:
    assert normalized_version_parts("v1.2.3+abcdef1") == [1, 2, 3]
    assert compare_versions("1.2.3", "1.2.3+abcdef1") == 0
    assert compare_versions("1.2.4", "1.2.3+abcdef1") == 1


def test_resolve_http_port_can_pick_an_available_port_when_requested_is_busy() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        occupied_port = int(listener.getsockname()[1])
        listener.listen(1)

        assert port_is_available(occupied_port) is False
        selected_port = resolve_http_port(
            occupied_port,
            prefer_available_http_port=True,
        )

    assert selected_port != occupied_port
    assert selected_port > occupied_port


def test_classify_startup_failure_reports_host_port_conflict(tmp_path: Path) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    control_plane_stderr.write_text("bind() failed: Address already in use\n", encoding="utf-8")
    manifest = {
        "http_port": 11434,
        "ready_probe_url": "http://127.0.0.1:11434/v1/models",
        "control_plane_stderr_path": str(control_plane_stderr),
    }

    report = classify_startup_failure(manifest, error_text="handshake failed")

    assert report.classification == "host_port_conflict"
    assert "11434" in report.summary
    assert "Address already in use" in report.log_excerpt


def test_classify_startup_failure_reports_worker_crash(tmp_path: Path) -> None:
    python_worker_stderr = tmp_path / "python-worker.stderr.log"
    python_worker_stderr.write_text("Traceback: worker bootstrap failed\n", encoding="utf-8")
    manifest = {
        "http_port": 11434,
        "ready_probe_url": "http://127.0.0.1:11434/v1/models",
        "python_worker_stderr_path": str(python_worker_stderr),
    }

    report = classify_startup_failure(manifest, error_text="handshake failed")

    assert report.classification == "worker_crash"
    assert "worker" in report.summary.lower()
    assert "Traceback" in report.log_excerpt


def test_classify_startup_failure_falls_back_to_hang_when_logs_are_empty() -> None:
    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
        },
        error_text="handshake failed",
    )

    assert report.classification == "startup_hang"
    assert "11434" in report.summary
