from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import worker.productization.startup_signals as startup_signals_module
from worker.productization.startup_signals import (
    StartupFailureReport,
    _read_last_nonempty_line,
    check_for_updates,
    classify_startup_failure,
    compare_versions,
    default_update_channel_path,
    normalized_version_parts,
    port_is_available,
    read_product_version,
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
    assert not hasattr(result, "__dict__")


def test_check_for_updates_reports_up_to_date_version(tmp_path: Path) -> None:
    channel_path = tmp_path / "stable.json"
    channel_path.write_text(
        json.dumps({"channel": "stable", "latest_version": "0.2.0"}),
        encoding="utf-8",
    )

    result = check_for_updates("0.2.0", channel_path)

    assert result.checked is True
    assert result.update_available is False
    assert result.summary == "Update: up to date"


def test_check_for_updates_reports_missing_latest_version(tmp_path: Path) -> None:
    channel_path = tmp_path / "stable.json"
    channel_path.write_text(json.dumps({"channel": "beta"}), encoding="utf-8")

    result = check_for_updates("0.1.0", channel_path)

    assert result.checked is False
    assert result.latest_version == ""
    assert result.channel == "beta"
    assert "does not declare latest_version" in result.detail


def test_read_product_version_reads_project_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "melix"\nversion = "1.2.3"\n', encoding="utf-8")

    assert read_product_version(tmp_path) == "1.2.3"


def test_read_product_version_raises_when_version_is_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "melix"\n', encoding="utf-8")

    try:
        read_product_version(tmp_path)
    except ValueError as exc:
        assert "Unable to read version" in str(exc)
    else:
        raise AssertionError("expected read_product_version to raise ValueError")


def test_default_update_channel_path_uses_stable_channel_json(tmp_path: Path) -> None:
    expected = tmp_path.resolve() / "infra/packaging/update-channels/stable.json"

    assert default_update_channel_path(tmp_path) == expected


def test_compare_versions_ignores_build_metadata_suffix() -> None:
    assert normalized_version_parts("v1.2.3+abcdef1") == [1, 2, 3]
    assert compare_versions("1.2.3+build.4", "1.2.3") == 0
    assert compare_versions("1.2.3", "1.2.3+abcdef1") == 0
    assert compare_versions("1.2.4", "1.2.3+abcdef1") == 1
    assert compare_versions("1.2.2", "1.2.3") == -1


def test_compare_versions_handles_suffixes_without_padding_lists() -> None:
    assert normalized_version_parts(" v2.10rc1.0-beta+build ") == [2, 10, 0]
    assert normalized_version_parts("release") == [0]
    assert compare_versions("2.10rc1", "2.9.99") == 1
    assert compare_versions("2.10", "2.10.0.0") == 0


def test_compare_versions_streams_parts_without_materialized_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_normalized_parts(value: str) -> list[int]:  # pragma: no cover - sentinel
        raise AssertionError(f"compare_versions materialized parts for {value}")

    monkeypatch.setattr(startup_signals_module, "normalized_version_parts", fail_normalized_parts)

    assert compare_versions("v9.10.1+build", "9.10.0.99") == 1
    assert compare_versions("2.10", "2.10.0.0") == 0


def test_compare_versions_does_not_allocate_streaming_part_generators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_iter_parts(value: str):  # pragma: no cover - sentinel
        raise AssertionError(f"compare_versions allocated part iterator for {value}")

    monkeypatch.setattr(startup_signals_module, "_iter_normalized_version_parts", fail_iter_parts)

    assert compare_versions("v1..2.0+build", "1.2") == 0
    assert compare_versions("3.0-alpha", "2.99.99") == 1


def test_compare_versions_identical_raw_values_skip_normalization() -> None:
    class StripForbiddenVersion(str):
        def strip(self, chars: str | None = None) -> str:  # pragma: no cover - sentinel
            raise AssertionError("compare_versions normalized exactly identical raw values")

    value = StripForbiddenVersion("v1.2.3+build")

    assert compare_versions(value, value) == 0


def test_compare_versions_identical_clean_values_skip_part_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_next_part(value: str, index: int):  # pragma: no cover - sentinel
        raise AssertionError(f"compare_versions parsed identical values for {value} at {index}")

    monkeypatch.setattr(startup_signals_module, "_next_normalized_version_part", fail_next_part)

    assert compare_versions(" v1.2.3+build ", "v1.2.3+build") == 0


def test_compare_versions_v_prefix_equivalent_values_skip_part_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_next_part(value: str, index: int):  # pragma: no cover - sentinel
        raise AssertionError(f"compare_versions parsed v-prefix equivalent values for {value} at {index}")

    monkeypatch.setattr(startup_signals_module, "_next_normalized_version_part", fail_next_part)

    assert compare_versions("v1.2.3+build", "1.2.3+build") == 0
    assert compare_versions("2.10.0", "v2.10.0") == 0


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


def test_resolve_http_port_returns_requested_port_when_preference_is_disabled() -> None:
    assert resolve_http_port(11434, prefer_available_http_port=False) == 11434


def test_resolve_http_port_raises_when_no_candidate_is_available() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as first_listener, socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as second_listener:
        first_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        first_listener.bind(("127.0.0.1", 0))
        occupied_port = int(first_listener.getsockname()[1])
        first_listener.listen(1)

        second_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        second_listener.bind(("127.0.0.1", occupied_port + 1))
        second_listener.listen(1)

        try:
            resolve_http_port(
                occupied_port,
                prefer_available_http_port=True,
                search_limit=2,
            )
        except RuntimeError as exc:
            assert str(occupied_port) in str(exc)
        else:
            raise AssertionError("expected resolve_http_port to raise RuntimeError")


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


def test_startup_failure_report_uses_slots_without_changing_dict_payload(tmp_path: Path) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    control_plane_stderr.write_text("fatal error: boot failed\n", encoding="utf-8")

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
        },
        error_text="handshake failed",
    )

    assert not hasattr(report, "__dict__")
    assert report.to_dict() == {
        "classification": "control_plane_crash",
        "summary": "Control plane crashed before startup completed.",
        "detail": "Melix never reached http://127.0.0.1:11434/v1/models. Inspect the control-plane logs for the crash cause.",
        "http_port": 11434,
        "ready_probe_url": "http://127.0.0.1:11434/v1/models",
        "primary_log_path": str(control_plane_stderr),
        "log_excerpt": "fatal error: boot failed",
    }


def test_startup_failure_report_to_dict_uses_direct_field_snapshot() -> None:
    report = StartupFailureReport(
        classification="control_plane_crash",
        summary="Control plane crashed before startup completed.",
        detail="Inspect the control-plane logs for the crash cause.",
        http_port=12436,
        ready_probe_url="http://127.0.0.1:12436/v1/models",
        primary_log_path="control-plane.stderr.log",
        log_excerpt="fatal error: control plane crashed",
    )

    assert not hasattr(startup_signals_module, "asdict")
    assert report.to_dict() == {
        "classification": "control_plane_crash",
        "summary": "Control plane crashed before startup completed.",
        "detail": "Inspect the control-plane logs for the crash cause.",
        "http_port": 12436,
        "ready_probe_url": "http://127.0.0.1:12436/v1/models",
        "primary_log_path": "control-plane.stderr.log",
        "log_excerpt": "fatal error: control plane crashed",
    }


def test_classify_startup_failure_skips_log_reads_when_error_text_reports_port_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("fatal error: should not be inspected\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: worker should not be inspected\n", encoding="utf-8")
    read_paths: list[str] = []

    def tracked_read(path: Path, *, chunk_size: int = 8192) -> str:
        read_paths.append(path.name)
        raise AssertionError("logs should not be read when error text already identifies the port conflict")

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", tracked_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="bind() failed: Address already in use",
    )

    assert report.classification == "host_port_conflict"
    assert report.log_excerpt == "bind() failed: Address already in use"
    assert read_paths == []


def test_classify_startup_failure_skips_logs_when_error_text_reports_control_plane_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("fatal error: stale control crash\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: stale worker crash\n", encoding="utf-8")

    def fail_read(path: Path, *, chunk_size: int = 8192) -> str:
        raise AssertionError(  # pragma: no cover
            f"logs should not be read when error text already identifies a crash: {path}"
        )

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", fail_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="fatal error: control plane crashed",
    )

    assert report.classification == "control_plane_crash"
    assert report.log_excerpt == "fatal error: control plane crashed"


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


def test_classify_startup_failure_skips_logs_when_error_text_reports_host_port_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("fatal error: should not be inspected\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: worker should not be inspected\n", encoding="utf-8")

    def fail_read(path: Path, *, chunk_size: int = 8192) -> str:
        message = f"startup logs should not be read for direct port conflicts: {path}"  # pragma: no cover
        raise AssertionError(message)  # pragma: no cover

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", fail_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="bind() failed: Address already in use",
    )

    assert report.classification == "host_port_conflict"
    assert report.log_excerpt == "bind() failed: Address already in use"


def test_classify_startup_failure_skips_worker_logs_for_host_port_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("bind() failed: Address already in use\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: worker should not be inspected\n", encoding="utf-8")
    read_paths: list[str] = []

    def tracked_read(path: Path, *, chunk_size: int = 8192) -> str:
        read_paths.append(path.name)
        if path == worker_stderr:
            raise AssertionError("worker log should not be read for host port conflicts")
        return _read_last_nonempty_line(path, chunk_size=chunk_size)

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", tracked_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="handshake failed",
    )

    assert report.classification == "host_port_conflict"
    assert read_paths == ["control-plane.stderr.log"]


def test_classify_startup_failure_skips_all_logs_when_error_text_identifies_host_port_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("fatal error: unrelated stale crash\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: worker should not be inspected\n", encoding="utf-8")

    def tracked_read(path: Path, *, chunk_size: int = 8192) -> str:
        raise AssertionError(f"logs should not be read when error_text already identifies a port conflict: {path}")

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", tracked_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="bind() failed: Address already in use",
    )

    assert report.classification == "host_port_conflict"
    assert report.log_excerpt == "bind() failed: Address already in use"


def test_classify_startup_failure_skips_worker_logs_for_control_plane_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    worker_stderr = tmp_path / "python-worker.stderr.log"
    control_plane_stderr.write_text("fatal error: crashed\n", encoding="utf-8")
    worker_stderr.write_text("Traceback: worker should not be inspected\n", encoding="utf-8")
    read_paths: list[str] = []

    def tracked_read(path: Path, *, chunk_size: int = 8192) -> str:
        read_paths.append(path.name)
        if path == worker_stderr:
            raise AssertionError("worker log should not be read for control-plane crashes")
        return _read_last_nonempty_line(path, chunk_size=chunk_size)

    monkeypatch.setattr(startup_signals_module, "_read_last_nonempty_line", tracked_read)

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
            "python_worker_stderr_path": str(worker_stderr),
        },
        error_text="handshake failed",
    )

    assert report.classification == "control_plane_crash"
    assert read_paths == ["control-plane.stderr.log"]


def test_classify_startup_failure_reports_control_plane_crash(tmp_path: Path) -> None:
    control_plane_stderr = tmp_path / "control-plane.stderr.log"
    control_plane_stderr.write_text("fatal error: crashed\n", encoding="utf-8")

    report = classify_startup_failure(
        {
            "http_port": 11434,
            "ready_probe_url": "http://127.0.0.1:11434/v1/models",
            "control_plane_stderr_path": str(control_plane_stderr),
        },
        error_text="handshake failed",
    )

    assert report.classification == "control_plane_crash"
    assert "Control plane crashed" in report.summary
    assert report.to_dict()["classification"] == "control_plane_crash"


def test_log_excerpt_skips_missing_paths_without_exists_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_log = tmp_path / "missing.stderr.log"
    existing_log = tmp_path / "control-plane.stderr.log"
    existing_log.write_text("booting\nready\n", encoding="utf-8")

    def fail_exists(self: Path) -> bool:
        raise AssertionError(  # pragma: no cover
            f"_log_excerpt should not preflight paths with exists(): {self}"
        )

    monkeypatch.setattr(Path, "exists", fail_exists)

    assert startup_signals_module._log_excerpt(missing_log, existing_log) == "ready"


def test_log_excerpt_preserves_multiple_log_order_without_list_join(tmp_path: Path) -> None:
    control_log = tmp_path / "control-plane.stderr.log"
    worker_log = tmp_path / "python-worker.stderr.log"
    control_log.write_text("booting\ncontrol ready\n", encoding="utf-8")
    worker_log.write_text("booting\nworker ready\n", encoding="utf-8")

    assert startup_signals_module._log_excerpt(control_log, worker_log) == "control ready | worker ready"


def test_log_excerpt_skips_empty_logs_during_single_pass_combine(tmp_path: Path) -> None:
    empty_log = tmp_path / "empty.stderr.log"
    worker_log = tmp_path / "python-worker.stderr.log"
    empty_log.write_text("\n\t\n", encoding="utf-8")
    worker_log.write_text("booting\nworker ready\n", encoding="utf-8")

    assert startup_signals_module._log_excerpt(empty_log, worker_log) == "worker ready"


def test_read_last_nonempty_line_ignores_trailing_blank_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "control-plane.stderr.log"
    log_path.write_text("booting\nready\n\n", encoding="utf-8")

    assert _read_last_nonempty_line(log_path) == "ready"


def test_read_last_nonempty_line_returns_empty_string_for_whitespace_only_file(tmp_path: Path) -> None:
    log_path = tmp_path / "control-plane.stderr.log"
    log_path.write_text("\n\t  \r\n", encoding="utf-8")

    assert _read_last_nonempty_line(log_path) == ""


def test_read_last_nonempty_line_decodes_invalid_utf8_with_replacement(tmp_path: Path) -> None:
    log_path = tmp_path / "python-worker.stderr.log"
    log_path.write_bytes(b"booting\nlast line \xff\n")

    assert _read_last_nonempty_line(log_path) == "last line �"


def test_read_last_nonempty_line_trims_byte_whitespace_without_python_byte_loop(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "python-worker.stderr.log"
    log_path.write_bytes(b"booting\nlast line\x85\xa0\n\t  \r\n")

    assert _read_last_nonempty_line(log_path, chunk_size=4) == "last line"


def test_log_excerpt_uses_read_fallback_without_exists_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "control-plane.stderr.log"
    log_path.write_text("booting\nready\n", encoding="utf-8")

    def fail_exists(self: Path) -> bool:
        raise AssertionError(f"log excerpt should read directly instead of checking exists(): {self}")

    monkeypatch.setattr(Path, "exists", fail_exists)

    assert startup_signals_module._log_excerpt(tmp_path / "missing.log", log_path) == "ready"


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
