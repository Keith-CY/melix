from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.integration.helpers as helpers


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)


def test_swift_product_binary_candidates_tolerates_missing_build_root(tmp_path: Path) -> None:
    build_root = tmp_path / "missing-build"

    assert helpers._swift_product_binary_candidates(build_root, "melix") == [
        build_root / "debug" / "melix"
    ]
    assert helpers._newest_executable_swift_product_binary(build_root, "melix") is None


def test_resolve_swift_product_binary_uses_scandir_fallback_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "mlx-text-worker-swift" / ".build"
    stale_flat = build_root / "debug" / "melix-text-worker-swift"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-text-worker-swift"
    _write_executable(stale_flat)
    _write_executable(preferred)
    os.utime(stale_flat, (1, 1))
    os.utime(preferred, (2, 2))

    def fail_glob(self: Path, pattern: str):
        raise AssertionError(f"Path.glob should not be used for Swift binary resolution: {pattern}")

    monkeypatch.setattr(Path, "glob", fail_glob)

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/mlx-text-worker-swift"),
        product_name="melix-text-worker-swift",
    )

    assert resolved == preferred


def test_resolve_scoped_swift_product_binary_uses_scandir_fallback_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / ".swiftpm" / "build" / "cli"
    preferred = build_root / "x86_64-apple-macosx" / "debug" / "melix"
    _write_executable(preferred)

    monkeypatch.setattr(
        helpers.swift_root_package,
        "swift_package_layout",
        lambda repo_root, scope: SimpleNamespace(scratch_path=build_root),
    )

    def fail_glob(self: Path, pattern: str):
        raise AssertionError(f"Path.glob should not be used for scoped Swift binary resolution: {pattern}")

    monkeypatch.setattr(Path, "glob", fail_glob)

    resolved = helpers.resolve_scoped_swift_product_binary(
        repo_root,
        scope="cli",
        product_name="melix",
    )

    assert resolved == preferred


def test_resolve_swift_product_binary_streams_candidates_without_candidate_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "control-plane-swift" / ".build"
    flat = build_root / "debug" / "melix-control-plane"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-control-plane"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (3, 3))
    os.utime(preferred, (3, 3))

    def fail_candidate_list(build_root: Path, product_name: str):
        raise AssertionError("binary resolution should not allocate the candidate list")

    monkeypatch.setattr(helpers, "_swift_product_binary_candidates", fail_candidate_list)
    with pytest.raises(AssertionError, match="candidate list"):
        helpers._swift_product_binary_candidates(build_root, "melix-control-plane")

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/control-plane-swift"),
        product_name="melix-control-plane",
    )

    assert resolved == preferred


def test_resolve_swift_product_binary_preserves_tie_breaker_without_path_parts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "control-plane-swift" / ".build"
    flat = build_root / "debug" / "melix-control-plane"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-control-plane"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (5, 5))
    os.utime(preferred, (5, 5))

    def fail_parts(self: Path):
        raise AssertionError("binary resolution should not allocate Path.parts per candidate")

    monkeypatch.setattr(Path, "parts", property(fail_parts))

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/control-plane-swift"),
        product_name="melix-control-plane",
    )

    assert resolved == preferred


def test_resolve_swift_product_binary_stats_each_candidate_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    build_root = repo_root / "services" / "mlx-text-worker-swift" / ".build"
    flat = build_root / "debug" / "melix-text-worker-swift"
    preferred = build_root / "arm64-apple-macosx" / "debug" / "melix-text-worker-swift"
    _write_executable(flat)
    _write_executable(preferred)
    os.utime(flat, (1, 1))
    os.utime(preferred, (2, 2))

    original_stat = helpers.os.stat
    product_stats = 0

    def counting_stat(path: str, *args: object, **kwargs: object):
        nonlocal product_stats
        if os.path.basename(path) == "melix-text-worker-swift":
            product_stats += 1
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(helpers.os, "stat", counting_stat)

    resolved = helpers.resolve_swift_product_binary(
        repo_root,
        package_path=Path("services/mlx-text-worker-swift"),
        product_name="melix-text-worker-swift",
    )

    assert resolved == preferred
    assert product_stats == 2


def test_live_stack_starts_and_stops_swift_vision_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "melix-text-worker-swift"
    _write_executable(binary)
    stack = helpers.LiveMelixStack(
        tmp_path,
        start_python_worker=False,
        environment_overrides={"MELIX_TEST_SENTINEL": "1"},
    )
    popen_calls: list[dict[str, object]] = []
    handshakes: list[Path] = []
    stopped: list[str] = []

    class FakeProcess:
        next_pid = 1000

        def __init__(self) -> None:
            self.pid = FakeProcess.next_pid
            FakeProcess.next_pid += 1

        def poll(self) -> None:
            return None

    tick = 0.0

    def fake_perf_counter() -> float:
        nonlocal tick
        tick += 0.1
        return tick

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        popen_calls.append({"command": command, **kwargs})
        return FakeProcess()

    def fake_wait_for_worker_handshake(socket_path: Path, **kwargs: object) -> None:
        handshakes.append(socket_path)

    def fake_wait_for_http_ready(http_port: int, **kwargs: object) -> None:
        assert kwargs["swift_vision_worker"] is stack.swift_vision_worker
        assert kwargs["swift_vision_worker_stdout_path"] == stack.swift_vision_worker_stdout_path
        assert kwargs["swift_vision_worker_stderr_path"] == stack.swift_vision_worker_stderr_path

    monkeypatch.setattr(helpers, "resolve_swift_product_binary", lambda *args, **kwargs: binary)
    monkeypatch.setattr(helpers.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(helpers, "wait_for_worker_handshake", fake_wait_for_worker_handshake)
    monkeypatch.setattr(helpers, "wait_for_http_ready", fake_wait_for_http_ready)
    monkeypatch.setattr(helpers.time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(helpers.time, "perf_counter_ns", lambda: 123)

    stack.start()

    swift_vision_call = next(
        call
        for call in popen_calls
        if call["env"].get("MELIX_SWIFT_WORKER_FAMILY") == "vision"  # type: ignore[union-attr]
    )
    assert handshakes == [stack.swift_socket_path, stack.swift_vision_socket_path]
    assert swift_vision_call["command"] == [str(binary)]
    assert swift_vision_call["env"]["MELIX_SWIFT_VISION_WORKER_SOCKET_PATH"] == str(  # type: ignore[index]
        stack.swift_vision_socket_path
    )
    assert swift_vision_call["env"]["MELIX_SWIFT_VISION_WORKER_METRICS_PATH"] == str(  # type: ignore[index]
        stack.swift_vision_worker_metrics_path
    )
    assert swift_vision_call["env"]["MELIX_SWIFT_VISION_WORKER_CACHE_ROOT"] == str(  # type: ignore[index]
        stack.swift_cache_root / "vision"
    )
    assert swift_vision_call["env"]["MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH"] == str(  # type: ignore[index]
        stack.runtime_state_root / "receipts" / "vision-payload.jsonl"
    )
    control_plane_call = next(
        call
        for call in popen_calls
        if "MELIX_HTTP_PORT" in call["env"]  # type: ignore[operator]
    )
    assert control_plane_call["env"]["MELIX_SWIFT_VISION_WORKER_SOCKET_PATH"] == str(  # type: ignore[index]
        stack.swift_vision_socket_path
    )
    assert stack.startup_timings["swift_vision_worker_ready_ms"] > 0.0

    monkeypatch.setattr(stack, "_stop_process", lambda name, process: stopped.append(name))
    stack.stop()

    assert "swift vision worker" in stopped
    assert stack.swift_vision_worker is None
    assert stack.swift_vision_worker_stdout is None
    assert stack.swift_vision_worker_stderr is None
    assert not stack.swift_vision_worker_stdout_path.exists()
    assert not stack.swift_vision_worker_stderr_path.exists()


def test_wait_for_http_model_states_reports_swift_vision_exit(tmp_path: Path) -> None:
    stdout_path = tmp_path / "vision.stdout.log"
    stderr_path = tmp_path / "vision.stderr.log"
    stdout_path.write_text("stdout", encoding="utf-8")
    stderr_path.write_text("stderr", encoding="utf-8")

    class ExitedProcess:
        def poll(self) -> int:
            return 1

    with pytest.raises(AssertionError) as exc:
        helpers.wait_for_http_model_states(
            12436,
            required_states={"model": "warm"},
            swift_vision_worker=ExitedProcess(),  # type: ignore[arg-type]
            swift_vision_worker_stdout_path=stdout_path,
            swift_vision_worker_stderr_path=stderr_path,
        )

    message = str(exc.value)
    assert "Swift vision worker exited before warm model was visible" in message
    assert "stderr" in message
