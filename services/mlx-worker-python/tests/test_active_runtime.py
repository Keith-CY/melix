from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

import worker.productization.active_runtime as active_runtime_module
from worker.productization.active_runtime import main, write_active_runtime_descriptor


def test_write_active_runtime_descriptor_is_atomic_private_and_complete(tmp_path: Path) -> None:
    output_path = tmp_path / "run" / "active-runtime.json"

    payload = write_active_runtime_descriptor(
        output_path=output_path,
        app_process_id=101,
        control_plane_process_id=202,
        python_worker_process_id=303,
        swift_text_worker_process_id=404,
        computer_broker_process_id=505,
        python_worker_socket_path="/tmp/python.sock",
        swift_text_worker_socket_path="/tmp/swift.sock",
        control_plane_socket_path="/tmp/control-plane.sock",
        service_base_url="http://127.0.0.1:12436/v1",
        now_unix_ms=lambda: 123_456,
    )

    assert payload == {
        "schema_version": "melix.active_runtime.v1",
        "app_process_id": 101,
        "control_plane_process_id": 202,
        "python_worker_process_id": 303,
        "swift_text_worker_process_id": 404,
        "computer_broker_process_id": 505,
        "python_worker_socket_path": "/tmp/python.sock",
        "swift_text_worker_socket_path": "/tmp/swift.sock",
        "control_plane_socket_path": "/tmp/control-plane.sock",
        "service_base_url": "http://127.0.0.1:12436/v1",
        "updated_at_unix_ms": 123_456,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    assert list(output_path.parent.glob(".active-runtime.json.*.tmp")) == []


def test_active_runtime_cli_replaces_existing_descriptor(tmp_path: Path) -> None:
    output_path = tmp_path / "active-runtime.json"
    output_path.write_text("stale\n", encoding="utf-8")
    output_path.chmod(0o644)

    assert main(
        [
            "--output-path",
            str(output_path),
            "--app-process-id",
            "11",
            "--control-plane-process-id",
            "22",
            "--python-worker-process-id",
            "33",
            "--swift-text-worker-process-id",
            "44",
            "--computer-broker-process-id",
            "55",
            "--python-worker-socket-path",
            "/tmp/python.sock",
            "--swift-text-worker-socket-path",
            "/tmp/swift.sock",
            "--service-base-url",
            "http://127.0.0.1:12436/v1",
        ]
    ) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "melix.active_runtime.v1"
    assert payload["app_process_id"] == 11
    assert payload["control_plane_process_id"] == 22
    assert payload["python_worker_process_id"] == 33
    assert payload["swift_text_worker_process_id"] == 44
    assert payload["computer_broker_process_id"] == 55
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


def test_write_active_runtime_descriptor_removes_temporary_file_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "run" / "active-runtime.json"

    def fail_json_dump(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise RuntimeError("synthetic serialization failure")

    monkeypatch.setattr(active_runtime_module.json, "dump", fail_json_dump)

    with pytest.raises(RuntimeError, match="synthetic serialization failure"):
        write_active_runtime_descriptor(
            output_path=output_path,
            app_process_id=101,
            control_plane_process_id=202,
            python_worker_process_id=303,
            swift_text_worker_process_id=404,
            python_worker_socket_path="/tmp/python.sock",
            swift_text_worker_socket_path="/tmp/swift.sock",
            service_base_url="http://127.0.0.1:12436/v1",
        )

    assert output_path.exists() is False
    assert list(output_path.parent.glob(".active-runtime.json.*.tmp")) == []
