from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / ".githooks" / "pre-commit"
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


def test_gate_allows_untracked_files(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    git_env = pre_commit_gate._git_env()
    subprocess.check_call(["git", "init"], cwd=tmp_path, stdout=subprocess.DEVNULL, env=git_env)
    (tmp_path / "tracked.py").write_text("print('tracked')\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "tracked.py"], cwd=tmp_path, env=git_env)
    (tmp_path / "local-probe.py").write_text("print('local')\n", encoding="utf-8")
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(
        pre_commit_gate,
        "run_performance_report",
        lambda root, changed_files: pre_commit_gate.PerformanceOutcome("ok", tmp_path / "report", 0),
    )

    def command_runner(command: str, cwd: Path):
        commands.append(command)
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 0
    assert commands == ["make swift-test", "make py-test", "make integration-test"]


def test_run_shell_command_scrubs_git_hook_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_DIR", "/tmp/melix-hook-git-dir")
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/melix-hook-work-tree")
    monkeypatch.setenv("GIT_INDEX_FILE", "/tmp/melix-hook-index")

    command = (
        f"{sys.executable} -c "
        "'import os, sys; "
        "sys.exit(any(os.environ.get(name) for name in "
        "(\"GIT_DIR\", \"GIT_WORK_TREE\", \"GIT_INDEX_FILE\")))'"
    )

    result = pre_commit_gate.run_shell_command(command, tmp_path)

    assert result.ok is True


def test_scrub_git_local_env_requires_keyword_env() -> None:
    with pytest.raises(TypeError):
        pre_commit_gate.scrub_git_local_env({"GIT_DIR": "/tmp/melix-hook-git-dir"})  # type: ignore[misc]


def test_gate_blocks_when_unstaged_tracked_files_are_present(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: ["scripts/pre_commit_gate.py"])

    def command_runner(command: str, cwd: Path):
        commands.append(command)
        return pre_commit_gate.CommandResult(command, True, 0, 0.0)

    assert pre_commit_gate.run_gate(tmp_path, env={}, command_runner=command_runner) == 1
    assert commands == []


def test_export_head_snapshot_uses_popen_context_on_tar_failure(monkeypatch, tmp_path: Path) -> None:
    class FakeStdout:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeArchive:
        def __init__(self) -> None:
            self.stdout = FakeStdout()
            self.exited = False
            self.waited = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            self.exited = True
            self.stdout.close()
            self.wait()

        def wait(self) -> int:
            self.waited = True
            return 0

    archive = FakeArchive()
    monkeypatch.setattr(pre_commit_gate.subprocess, "Popen", lambda *args, **kwargs: archive)

    def raise_from_tar(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=2, cmd=["tar"])

    monkeypatch.setattr(pre_commit_gate.subprocess, "run", raise_from_tar)

    try:
        pre_commit_gate.export_head_snapshot(tmp_path, tmp_path / "snapshot")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("expected tar failure to propagate")

    assert archive.exited is True
    assert archive.stdout.closed is True
    assert archive.waited is True


def test_export_index_snapshot_can_preserve_head_diff_for_staged_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    snapshot = tmp_path / "snapshot"
    source.mkdir()
    git_env = pre_commit_gate._git_env()
    subprocess.check_call(["git", "init", "-q"], cwd=source, env=git_env)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=source, env=git_env)
    subprocess.check_call(["git", "config", "user.email", "test@example.invalid"], cwd=source, env=git_env)
    (source / "changed.py").write_text("value = 1\n", encoding="utf-8")
    (source / "nested").mkdir()
    (source / "deleted.py").write_text("remove_me = True\n", encoding="utf-8")
    (source / "nested" / "deleted.py").write_text("nested_remove_me = True\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "-A"], cwd=source, env=git_env)
    subprocess.check_call(["git", "commit", "-q", "-m", "base"], cwd=source, env=git_env)
    (source / "changed.py").write_text("value = 1\nadded = 2\n", encoding="utf-8")
    (source / "added.py").write_text("created = True\n", encoding="utf-8")
    (source / "deleted.py").unlink()
    (source / "nested" / "deleted.py").unlink()
    subprocess.check_call(["git", "add", "-A"], cwd=source, env=git_env)

    pre_commit_gate.export_index_snapshot(source, snapshot, git_backed=True)

    diff = subprocess.check_output(
        ["git", "diff", "--name-status"],
        cwd=snapshot,
        text=True,
        env=git_env,
    )
    assert "M\tchanged.py" in diff
    assert "A\tadded.py" in diff
    assert "D\tdeleted.py" in diff
    assert "D\tnested/deleted.py" in diff
    assert not (snapshot / "nested").exists()
    added_diff = subprocess.check_output(
        ["git", "diff", "--unified=0", "--", "added.py"],
        cwd=snapshot,
        text=True,
        env=git_env,
    )
    assert "+created = True" in added_diff


def test_performance_probe_failure_writes_traceback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pre_commit_gate, "_report_run_dir", lambda root: tmp_path / "run")
    monkeypatch.setattr(
        pre_commit_gate,
        "build_scope_report",
        lambda registry_path, changed_files: {
            "changed_files": changed_files,
            "force_all": False,
            "matched_probe_ids": ["probe-one"],
            "selected_probes": [{"id": "probe-one", "name": "Probe one", "metrics": []}],
        },
    )
    monkeypatch.setattr(
        pre_commit_gate,
        "load_probe_registry",
        lambda registry_path: (SimpleNamespace(probe_id="probe-one"),),
    )
    snapshot_modes: list[bool] = []

    def fake_export_index_snapshot(root: Path, destination: Path, *, git_backed: bool = False) -> None:
        snapshot_modes.append(git_backed)
        destination.mkdir()

    monkeypatch.setattr(pre_commit_gate, "export_index_snapshot", fake_export_index_snapshot)
    monkeypatch.setattr(pre_commit_gate, "export_head_snapshot", lambda root, destination: destination.mkdir())

    def fail_probe(**kwargs):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(pre_commit_gate, "run_probe_job", fail_probe)
    monkeypatch.setattr(
        pre_commit_gate,
        "build_performance_report",
        lambda scope, probe_results: {"summary": {"status": "verification_failed"}, "rows": []},
    )
    monkeypatch.setattr(
        pre_commit_gate,
        "write_report_outputs",
        lambda report, report_dir: {"markdown": report_dir / "report.md"},
    )
    monkeypatch.setattr(pre_commit_gate, "render_terminal_report", lambda report: "")

    outcome = pre_commit_gate.run_performance_report(tmp_path, ["scripts/pre_commit_gate.py"])

    error_text = (tmp_path / "run" / "probes" / "probe-one.error.txt").read_text(encoding="utf-8")
    assert outcome.status == "verification_failed"
    assert snapshot_modes == [True]
    assert "Traceback (most recent call last)" in error_text
    assert "RuntimeError: probe exploded" in error_text


def test_shell_hook_uses_repo_cache_and_python_312_by_default(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "rev-parse" && "$2" == "--show-toplevel" ]]; then\n'
        f'  printf "%s\\n" "{tmp_path}"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "uname").write_text("#!/usr/bin/env bash\nprintf Linux\n", encoding="utf-8")
    uv_log = tmp_path / "uv-env.txt"
    (bin_dir / "uv").write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$UV_CACHE_DIR|$UV_PYTHON|$*" > "{uv_log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    for executable in (bin_dir / "git", bin_dir / "uname", bin_dir / "uv"):
        executable.chmod(0o755)
    (tmp_path / "services/mlx-worker-python").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()

    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=tmp_path,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "MELIX_PRE_COMMIT_FORCE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert uv_log.read_text(encoding="utf-8") == (
        f"{tmp_path}/.uv-cache|3.12|run --frozen --project services/mlx-worker-python --extra mlx "
        "python scripts/pre_commit_gate.py\n"
    )


def test_shell_hook_honors_python_override(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "rev-parse" && "$2" == "--show-toplevel" ]]; then\n'
        f'  printf "%s\\n" "{tmp_path}"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "uv").write_text(
        "#!/usr/bin/env bash\n"
        '[[ "$UV_PYTHON" == "3.13" ]]\n',
        encoding="utf-8",
    )
    for executable in (bin_dir / "git", bin_dir / "uv"):
        executable.chmod(0o755)

    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "MELIX_PRE_COMMIT_FORCE": "1",
            "MELIX_PRE_COMMIT_UV_PYTHON": "3.13",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def test_gate_blocks_performance_regression_without_override(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    monkeypatch.setattr(pre_commit_gate, "resolve_host_gate", lambda env: pre_commit_gate.HostGate(True, "forced"))
    monkeypatch.setattr(pre_commit_gate, "staged_changed_files", lambda root: ["services/example.py"])
    monkeypatch.setattr(pre_commit_gate, "unstaged_tracked_files", lambda root: [])
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
