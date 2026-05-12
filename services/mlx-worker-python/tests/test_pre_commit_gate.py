from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "pre_commit_gate.py"
MODULE_SPEC = importlib.util.spec_from_file_location("pre_commit_gate", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
pre_commit_gate = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = pre_commit_gate
MODULE_SPEC.loader.exec_module(pre_commit_gate)


def test_host_gate_enforces_only_on_large_macos(monkeypatch) -> None:
    monkeypatch.setattr(pre_commit_gate.platform, "system", lambda: "Linux")

    skipped = pre_commit_gate.resolve_host_gate({})

    assert skipped.enforced is False
    assert "not macOS" in skipped.reason

    monkeypatch.setattr(pre_commit_gate.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pre_commit_gate, "physical_memory_bytes", lambda: 127 * 1024**3)

    small_mac = pre_commit_gate.resolve_host_gate({})

    assert small_mac.enforced is False
    assert "below" in small_mac.reason

    monkeypatch.setattr(pre_commit_gate, "physical_memory_bytes", lambda: 128 * 1024**3)

    large_mac = pre_commit_gate.resolve_host_gate({})

    assert large_mac.enforced is True
    assert "128.0 GiB" in large_mac.reason


def test_gate_skips_without_running_commands_when_host_is_not_enforced(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(False, "not macOS"))

    def command_runner(command: str, cwd: Path):
        commands.append(command)
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 0
    assert commands == []


def test_gate_blocks_when_full_test_command_fails(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
    monkeypatch.setattr(pre_commit_gate, "untracked_files", lambda root: [])
    monkeypatch.setattr(
        pre_commit_gate,
        "run_performance_report",
        lambda root, changed_files: (_ for _ in ()).throw(AssertionError("performance should not run")),
    )

    def command_runner(command: str, cwd: Path):
        commands.append(command)
        ok = command != "make py-test"
        return pre_commit_gate.CommandResult(command, ok, 0 if ok else 1, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 1
    assert commands == ["make swift-test", "make py-test"]


def test_gate_blocks_when_untracked_files_are_present(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
    monkeypatch.setattr(pre_commit_gate, "untracked_files", lambda root: ["scripts/local-probe.py"])

    def command_runner(command: str, cwd: Path):
        commands.append(command)
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 1
    assert commands == []


def test_gate_blocks_performance_regression_without_override(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
    monkeypatch.setattr(pre_commit_gate, "untracked_files", lambda root: [])
    monkeypatch.setattr(
        pre_commit_gate,
        "run_performance_report",
        lambda root, changed_files: pre_commit_gate.PerformanceOutcome("regression", report_dir, 1),
    )

    def command_runner(command: str, cwd: Path):
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 1


def test_gate_blocks_performance_regression_override_without_reason(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
    monkeypatch.setattr(pre_commit_gate, "untracked_files", lambda root: [])
    monkeypatch.setattr(
        pre_commit_gate,
        "run_performance_report",
        lambda root, changed_files: pre_commit_gate.PerformanceOutcome("regression", report_dir, 1),
    )

    def command_runner(command: str, cwd: Path):
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert (
        pre_commit_gate.run_gate(
            tmp_path,
            env={"MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION": "1"},
            command_runner=command_runner,
        )
        == 1
    )


def test_gate_allows_performance_regression_with_explicit_override_and_reason(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "report"
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
    monkeypatch.setattr(pre_commit_gate, "untracked_files", lambda root: [])
    monkeypatch.setattr(
        pre_commit_gate,
        "run_performance_report",
        lambda root, changed_files: pre_commit_gate.PerformanceOutcome("regression", report_dir, 1),
    )

    def command_runner(command: str, cwd: Path):
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert (
        pre_commit_gate.run_gate(
            tmp_path,
            env={
                "MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION": "1",
                "MELIX_PRE_COMMIT_PERF_REGRESSION_REASON": "expected extra validation work",
            },
            command_runner=command_runner,
        )
        == 0
    )
