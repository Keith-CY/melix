#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.pr_scoped_performance import (  # noqa: E402
    build_performance_report,
    build_scope_report,
    load_probe_registry,
    render_terminal_report,
    run_probe_job,
    write_report_outputs,
)
from worker.productization.git_env import scrub_git_local_env  # noqa: E402


MEMORY_THRESHOLD_BYTES = 128 * 1024**3
FULL_TEST_COMMANDS = ("make swift-test", "make py-test", "make integration-test")
REGISTRY_PATH = Path("infra/perf/pr_scoped_probes.json")
REPORT_ROOT = Path(".runtime/pre-commit-performance")


@dataclass(frozen=True)
class HostGate:
    enforced: bool
    reason: str


@dataclass(frozen=True)
class CommandResult:
    command: str
    ok: bool
    returncode: int
    elapsed_seconds: float


@dataclass(frozen=True)
class PerformanceOutcome:
    status: str
    report_dir: Path
    selected_probe_count: int


class GateError(RuntimeError):
    pass


def _env_flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def format_bytes(byte_count: int) -> str:
    gib = byte_count / (1024**3)
    return f"{gib:.1f} GiB"


def physical_memory_bytes() -> int:
    try:
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GateError(f"Unable to read macOS physical memory with sysctl: {exc}") from exc
    try:
        return int(raw)
    except ValueError as exc:
        raise GateError(f"Unexpected hw.memsize value: {raw!r}") from exc


def resolve_host_gate(env: Mapping[str, str] | None = None) -> HostGate:
    env = os.environ if env is None else env
    if _env_flag(env, "MELIX_PRE_COMMIT_FORCE"):
        return HostGate(True, "forced by MELIX_PRE_COMMIT_FORCE")

    system = platform.system()
    if system != "Darwin":
        return HostGate(False, f"host is {system or 'unknown'}, not macOS")

    memory_bytes = physical_memory_bytes()
    if memory_bytes < MEMORY_THRESHOLD_BYTES:
        return HostGate(
            False,
            f"macOS host memory is {format_bytes(memory_bytes)}, below {format_bytes(MEMORY_THRESHOLD_BYTES)}",
        )
    return HostGate(True, f"macOS host memory is {format_bytes(memory_bytes)}")


def run_git(root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, env=_git_env())


def _git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def repo_root() -> Path:
    return Path(run_git(Path.cwd(), ["rev-parse", "--show-toplevel"]).strip())


def staged_changed_files(root: Path) -> list[str]:
    output = run_git(root, ["diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def unstaged_tracked_files(root: Path) -> list[str]:
    output = run_git(root, ["diff", "--name-only"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def run_shell_command(command: str, cwd: Path) -> CommandResult:
    print(f"[pre-commit] running: {command}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, shell=True, env=scrub_git_local_env())
    elapsed = time.perf_counter() - started
    print(
        f"[pre-commit] completed rc={completed.returncode} elapsed={elapsed:.1f}s: {command}",
        flush=True,
    )
    return CommandResult(
        command=command,
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        elapsed_seconds=elapsed,
    )


def export_head_snapshot(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
    ) as archive:
        assert archive.stdout is not None
        extract = subprocess.run(
            ["tar", "-xf", "-", "-C", os.fspath(destination)],
            stdin=archive.stdout,
        )
        archive.stdout.close()
        archive_rc = archive.wait()
    if archive_rc != 0:
        raise GateError(f"git archive HEAD failed with exit {archive_rc}")
    if extract.returncode != 0:
        raise GateError(f"tar extraction for HEAD snapshot failed with exit {extract.returncode}")


def _initialize_snapshot_git_repo(source_root: Path, destination: Path) -> None:
    subprocess.check_call(["git", "init", "-q"], cwd=destination, env=scrub_git_local_env())
    source_head = run_git(source_root, ["rev-parse", "HEAD"]).strip()
    subprocess.check_call(["git", "add", "-A"], cwd=destination, env=scrub_git_local_env())
    subprocess.check_call(
        [
            "git",
            "-c",
            "user.name=Melix Pre-Commit",
            "-c",
            "user.email=melix-pre-commit@example.invalid",
            "commit",
            "-q",
            "-m",
            f"Snapshot {source_head}",
        ],
        cwd=destination,
        env=scrub_git_local_env(),
    )


def _tracked_paths_at_revision(root: Path, revision: str) -> set[str]:
    output = run_git(root, ["ls-tree", "-r", "--name-only", revision])
    return {line for line in output.splitlines() if line}


def _tracked_index_paths(root: Path) -> set[str]:
    output = run_git(root, ["ls-files"])
    return {line for line in output.splitlines() if line}


def _staged_added_paths(root: Path) -> set[str]:
    output = run_git(root, ["diff", "--cached", "--name-only", "--diff-filter=A"])
    return {line for line in output.splitlines() if line}


def _remove_paths_not_in_index(root: Path, destination: Path) -> None:
    removed_paths = _tracked_paths_at_revision(root, "HEAD") - _tracked_index_paths(root)
    for rel_path in sorted(removed_paths, reverse=True):
        target = destination / rel_path
        if target.is_file() or target.is_symlink():
            target.unlink()


def _mark_added_paths_intent_to_add(root: Path, destination: Path) -> None:
    added_paths = _staged_added_paths(root)
    if not added_paths:
        return
    subprocess.check_call(
        ["git", "add", "--intent-to-add", "--", *sorted(added_paths)],
        cwd=destination,
        env=scrub_git_local_env(),
    )


def export_index_snapshot(root: Path, destination: Path, *, git_backed: bool = False) -> None:
    export_head_snapshot(root, destination)
    if git_backed:
        _initialize_snapshot_git_repo(root, destination)
    _remove_paths_not_in_index(root, destination)
    prefix = os.fspath(destination) + os.sep
    try:
        subprocess.check_call(["git", "checkout-index", "--all", "--force", f"--prefix={prefix}"], cwd=root)
    except subprocess.CalledProcessError as exc:
        raise GateError(f"git checkout-index snapshot failed with exit {exc.returncode}") from exc
    if git_backed:
        _mark_added_paths_intent_to_add(root, destination)


def _report_run_dir(root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        short_head = run_git(root, ["rev-parse", "--short", "HEAD"]).strip()
    except subprocess.CalledProcessError:
        short_head = "no-head"
    return root / REPORT_ROOT / f"{timestamp}-{short_head}"


def run_full_tests(
    root: Path,
    *,
    command_runner: Callable[[str, Path], CommandResult] = run_shell_command,
) -> bool:
    for command in FULL_TEST_COMMANDS:
        result = command_runner(command, root)
        if not result.ok:
            print(f"[pre-commit] full test command failed: {command}", file=sys.stderr)
            return False
    return True


def run_performance_report(root: Path, changed_files: list[str]) -> PerformanceOutcome:
    run_dir = _report_run_dir(root)
    scope_dir = run_dir / "scope"
    probes_dir = run_dir / "probes"
    report_dir = run_dir / "report"
    scope_dir.mkdir(parents=True, exist_ok=True)
    probes_dir.mkdir(parents=True, exist_ok=True)

    changed_files_path = scope_dir / "changed-files.json"
    changed_files_path.write_text(json.dumps(changed_files, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    registry_path = root / REGISTRY_PATH
    scope = build_scope_report(registry_path=registry_path, changed_files=changed_files)
    (scope_dir / "scope.json").write_text(json.dumps(scope, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    results: list[dict[str, object]] = []
    selected_probes = scope.get("selected_probes", [])
    selected_probe_count = len(selected_probes) if isinstance(selected_probes, list) else 0
    if selected_probe_count:
        with tempfile.TemporaryDirectory(prefix="melix-pre-commit-probes-") as probe_temp:
            probe_temp_root = Path(probe_temp)
            head_repo = probe_temp_root / "head"
            export_index_snapshot(root, head_repo, git_backed=True)
            base_repo = probe_temp_root / "base"
            export_head_snapshot(root, base_repo)
            probes = {probe.probe_id: probe for probe in load_probe_registry(registry_path)}
            for probe_entry in selected_probes:
                if not isinstance(probe_entry, dict):
                    continue
                probe_id = str(probe_entry.get("id", "")).strip()
                if not probe_id:
                    continue
                print(f"[pre-commit] running performance probe: {probe_id}", flush=True)
                try:
                    result, _success = run_probe_job(
                        registry_path=registry_path,
                        probe_id=probe_id,
                        base_repo=base_repo,
                        head_repo=head_repo,
                    )
                    results.append(result)
                    (probes_dir / f"{probe_id}.json").write_text(
                        json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                except Exception:  # noqa: BLE001
                    exc_text = traceback.format_exc()
                    error_path = probes_dir / f"{probe_id}.error.txt"
                    error_path.write_text(exc_text, encoding="utf-8")
                    error_summary = exc_text.rstrip().splitlines()[-1] if exc_text.strip() else "unknown error"
                    print(
                        f"[pre-commit] performance probe failed before result: {probe_id}: {error_summary}",
                        file=sys.stderr,
                    )
                    if probe_id not in probes:
                        print(f"[pre-commit] unknown registered probe during report generation: {probe_id}", file=sys.stderr)

    report = build_performance_report(scope=scope, probe_results=results)
    outputs = write_report_outputs(report, report_dir)
    print(render_terminal_report(report), end="")
    print(f"[pre-commit] performance report: {outputs['markdown']}", flush=True)
    summary = report.get("summary", {})
    status = str(summary.get("status", "ok"))
    return PerformanceOutcome(
        status=status,
        report_dir=report_dir,
        selected_probe_count=selected_probe_count,
    )


def run_gate(
    root: Path,
    *,
    env: Mapping[str, str] | None = None,
    command_runner: Callable[[str, Path], CommandResult] = run_shell_command,
) -> int:
    env = os.environ if env is None else env
    host_gate = resolve_host_gate(env)
    if not host_gate.enforced:
        print(f"[pre-commit] skipped: {host_gate.reason}")
        return 0
    print(f"[pre-commit] enforced: {host_gate.reason}")

    changed_files = staged_changed_files(root)
    if not changed_files:
        print("[pre-commit] skipped: no staged files")
        return 0

    dirty_files = unstaged_tracked_files(root)
    if dirty_files:
        print(
            "[pre-commit] refusing to run with unstaged changes; "
            "stage or stash them so the gate validates the exact commit content.",
            file=sys.stderr,
        )
        for path in dirty_files[:20]:
            print(f"[pre-commit] unstaged: {path}", file=sys.stderr)
        if len(dirty_files) > 20:
            print(f"[pre-commit] unstaged: ... (+{len(dirty_files) - 20} more)", file=sys.stderr)
        return 1

    if not run_full_tests(root, command_runner=command_runner):
        return 1

    outcome = run_performance_report(root, changed_files)
    if outcome.status == "ok":
        return 0

    if outcome.status == "regression" and _env_flag(env, "MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION"):
        reason = env.get("MELIX_PRE_COMMIT_PERF_REGRESSION_REASON", "").strip()
        if not reason:
            print(
                "[pre-commit] MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION requires "
                "MELIX_PRE_COMMIT_PERF_REGRESSION_REASON so the intentional performance tradeoff is recorded.",
                file=sys.stderr,
            )
            print(f"[pre-commit] report directory: {outcome.report_dir}", file=sys.stderr)
            return 1
        print(
            "[pre-commit] allowing reported performance regression because "
            f"MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION is set: {reason}"
        )
        return 0

    if outcome.status == "regression":
        print(
            "[pre-commit] performance regression detected. Analyze the report before committing; "
            "if the regression is intentional and acceptable, rerun commit with "
            "MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1 and MELIX_PRE_COMMIT_PERF_REGRESSION_REASON.",
            file=sys.stderr,
        )
    else:
        print(f"[pre-commit] performance report status blocks commit: {outcome.status}", file=sys.stderr)
    print(f"[pre-commit] report directory: {outcome.report_dir}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        return run_gate(repo_root())
    except GateError as exc:
        print(f"[pre-commit] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
