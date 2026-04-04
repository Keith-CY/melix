from __future__ import annotations

from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from worker.productization.homebrew_formula import read_melix_version, render_homebrew_formula
from worker.productization.homebrew_service import (
    DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME,
    ManagedServiceProcess,
    ManagedServiceProcessGroup,
    build_homebrew_service_manifest,
    build_homebrew_service_specs,
    ensure_runtime_directories,
    run_homebrew_service_bundle,
)
from worker.productization.install_assets import LaunchAgentSpec


def test_read_melix_version_reads_root_pyproject_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text('[project]\nname = "melix"\nversion = "0.4.2"\n', encoding="utf-8")

    assert read_melix_version(repo_root) == "0.4.2"


def test_read_melix_version_raises_when_version_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text('[project]\nname = "melix"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to read version"):
        read_melix_version(repo_root)


def test_render_homebrew_formula_includes_service_wrapper_and_local_source_url() -> None:
    formula = render_homebrew_formula(version="0.1.0")

    assert 'url "file://#{repo_root}"' in formula
    assert 'version "0.1.0"' in formula
    assert 'opt_bin/"melix-homebrew-service"' in formula
    assert 'libexec/"scripts/melix_homebrew_service.py"' in formula


def test_build_homebrew_service_specs_use_homebrew_instance_and_installed_binaries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "services/mlx-worker-python").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    layout, specs = build_homebrew_service_specs(
        repo_root=repo_root,
        bin_dir=bin_dir,
        home_dir=home_dir,
        http_port=18443,
    )
    manifest = build_homebrew_service_manifest(layout, specs)
    spec_map = {spec.label: spec for spec in specs}

    assert layout.service_instance_name == DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME
    assert set(spec_map) == {
        "io.melix.homebrew.swift-text-worker",
        "io.melix.homebrew.python-worker",
        "io.melix.homebrew.control-plane",
    }
    assert spec_map["io.melix.homebrew.swift-text-worker"].program_arguments == [
        str(bin_dir / "melix-text-worker-swift")
    ]
    assert spec_map["io.melix.homebrew.control-plane"].program_arguments == [
        str(bin_dir / "melix-control-plane")
    ]
    assert spec_map["io.melix.homebrew.python-worker"].program_arguments[:6] == [
        "/usr/bin/env",
        "uv",
        "run",
        "--project",
        str(repo_root / "services/mlx-worker-python"),
        "python",
    ]
    assert manifest["ready_probe_url"] == "http://127.0.0.1:18443/v1/models"


def test_managed_service_process_group_starts_and_shuts_down_fixture_processes(tmp_path: Path) -> None:
    marker_path = tmp_path / "started.marker"
    spec = LaunchAgentSpec(
        label="io.melix.fixture",
        plist_path=tmp_path / "fixture.plist",
        program_arguments=[
            sys.executable,
            "-c",
            (
                "import pathlib,time;"
                f"pathlib.Path(r'{marker_path}').write_text('started', encoding='utf-8');"
                "time.sleep(60)"
            ),
        ],
        environment={},
        working_directory=tmp_path,
        stdout_path=tmp_path / "fixture.stdout.log",
        stderr_path=tmp_path / "fixture.stderr.log",
    )
    layout, _ = build_homebrew_service_specs(
        repo_root=tmp_path / "repo",
        bin_dir=tmp_path / "bin",
        home_dir=tmp_path / "home",
    )
    ensure_runtime_directories(layout)
    group = ManagedServiceProcessGroup([spec])
    group.start()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not marker_path.exists():
        time.sleep(0.05)

    shutdown_results = group.shutdown()

    assert marker_path.exists()
    assert shutdown_results[0][0] == "io.melix.fixture"
    assert shutdown_results[0][1] is not None


def test_managed_service_process_group_rejects_double_start(tmp_path: Path) -> None:
    marker_path = tmp_path / "double-start.marker"
    spec = LaunchAgentSpec(
        label="io.melix.fixture.double-start",
        plist_path=tmp_path / "double-start.plist",
        program_arguments=[
            sys.executable,
            "-c",
            (
                "import pathlib,time;"
                f"pathlib.Path(r'{marker_path}').write_text('started', encoding='utf-8');"
                "time.sleep(60)"
            ),
        ],
        environment={},
        working_directory=tmp_path,
        stdout_path=tmp_path / "double-start.stdout.log",
        stderr_path=tmp_path / "double-start.stderr.log",
    )
    group = ManagedServiceProcessGroup([spec])
    group.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            group.start()
    finally:
        group.shutdown()


def test_managed_service_process_group_reports_child_failures(tmp_path: Path) -> None:
    spec = LaunchAgentSpec(
        label="io.melix.fixture.failure",
        plist_path=tmp_path / "failure.plist",
        program_arguments=[sys.executable, "-c", "import sys; sys.exit(23)"],
        environment={},
        working_directory=tmp_path,
        stdout_path=tmp_path / "failure.stdout.log",
        stderr_path=tmp_path / "failure.stderr.log",
    )
    group = ManagedServiceProcessGroup([spec])
    group.start()

    deadline = time.monotonic() + 5.0
    failures: list[tuple[str, int]] = []
    while time.monotonic() < deadline:
        failures = group.poll_failures()
        if failures:
            break
        time.sleep(0.05)

    shutdown_results = group.shutdown()

    assert failures == [("io.melix.fixture.failure", 23)]
    assert shutdown_results == [("io.melix.fixture.failure", 23)]


def test_managed_service_process_group_kills_hung_process_after_timeout(tmp_path: Path) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def poll(self) -> int | None:
            if self.killed:
                return 9
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd=["fixture"], timeout=timeout)

        def kill(self) -> None:
            self.killed = True

    stdout_handle = (tmp_path / "hung.stdout.log").open("ab")
    stderr_handle = (tmp_path / "hung.stderr.log").open("ab")
    process = FakeProcess()
    spec = LaunchAgentSpec(
        label="io.melix.fixture.hung",
        plist_path=tmp_path / "hung.plist",
        program_arguments=["fixture"],
        environment={},
        working_directory=tmp_path,
        stdout_path=tmp_path / "hung.stdout.log",
        stderr_path=tmp_path / "hung.stderr.log",
    )
    group = ManagedServiceProcessGroup([])
    group._entries = [
        ManagedServiceProcess(
            spec=spec,
            process=process,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
        )
    ]

    shutdown_results = group.shutdown(grace_seconds=0.01)

    assert process.terminated is True
    assert process.killed is True
    assert shutdown_results == [("io.melix.fixture.hung", 9)]


def test_run_homebrew_service_bundle_returns_first_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class FakeGroup:
        def __init__(self, specs: list[LaunchAgentSpec]) -> None:
            seen["specs"] = specs

        def start(self) -> None:
            seen["started"] = True

        def poll_failures(self) -> list[tuple[str, int]]:
            return [("io.melix.fixture.failure", 17)]

        def shutdown(self, *, grace_seconds: float = 5.0) -> list[tuple[str, int | None]]:
            seen["grace_seconds"] = grace_seconds
            return [("io.melix.fixture.failure", 17)]

    handlers: dict[int, object] = {}

    def fake_signal(sig: int, handler: object) -> object:
        previous = handlers.get(sig, f"previous-{sig}")
        handlers[sig] = handler
        return previous

    monkeypatch.setattr(
        "worker.productization.homebrew_service.ManagedServiceProcessGroup",
        FakeGroup,
    )
    monkeypatch.setattr("worker.productization.homebrew_service.signal.signal", fake_signal)

    result = run_homebrew_service_bundle([], grace_seconds=1.5, poll_interval_seconds=0.01)

    assert result == 17
    assert seen["started"] is True
    assert seen["grace_seconds"] == 1.5
    assert handlers[signal.SIGINT] == f"previous-{signal.SIGINT}"
    assert handlers[signal.SIGTERM] == f"previous-{signal.SIGTERM}"


def test_run_homebrew_service_bundle_returns_zero_after_signal_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    handlers: dict[int, object] = {}

    class FakeGroup:
        def __init__(self, specs: list[LaunchAgentSpec]) -> None:
            seen["specs"] = specs

        def start(self) -> None:
            seen["started"] = True

        def poll_failures(self) -> list[tuple[str, int]]:
            return []

        def shutdown(self, *, grace_seconds: float = 5.0) -> list[tuple[str, int | None]]:
            seen["grace_seconds"] = grace_seconds
            return [("io.melix.fixture.stop", 0)]

    def fake_signal(sig: int, handler: object) -> object:
        previous = handlers.get(sig, f"previous-{sig}")
        handlers[sig] = handler
        return previous

    def fake_sleep(_seconds: float) -> None:
        handlers[signal.SIGTERM](signal.SIGTERM, object())

    monkeypatch.setattr(
        "worker.productization.homebrew_service.ManagedServiceProcessGroup",
        FakeGroup,
    )
    monkeypatch.setattr("worker.productization.homebrew_service.signal.signal", fake_signal)
    monkeypatch.setattr("worker.productization.homebrew_service.time.sleep", fake_sleep)

    result = run_homebrew_service_bundle([], grace_seconds=2.5, poll_interval_seconds=0.01)

    assert result == 0
    assert seen["started"] is True
    assert seen["grace_seconds"] == 2.5
    assert handlers[signal.SIGINT] == f"previous-{signal.SIGINT}"
    assert handlers[signal.SIGTERM] == f"previous-{signal.SIGTERM}"
