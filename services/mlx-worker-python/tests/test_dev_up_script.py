from __future__ import annotations

import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev_up.sh"


def run_script_snippet(repo_root: Path, snippet: str) -> subprocess.CompletedProcess[str]:
    command = f'''
source "{SCRIPT_PATH}"
ROOT="{repo_root}"
{snippet}
'''
    return subprocess.run(
        ["bash", "-c", command],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_build_swift_launch_command_defaults_to_swift_run(tmp_path: Path) -> None:
    result = run_script_snippet(
        tmp_path,
        'mapfile -t command < <(build_swift_launch_command "services/mlx-text-worker-swift" "melix-text-worker-swift"); printf "%s\\n" "${command[@]}"',
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "swift",
        "run",
        "--package-path",
        f"{tmp_path}/services/mlx-text-worker-swift",
        "melix-text-worker-swift",
    ]


def test_build_swift_launch_command_prefers_built_binary_when_requested(tmp_path: Path) -> None:
    binary_path = tmp_path / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/melix-text-worker-swift"
    make_executable(binary_path)

    result = run_script_snippet(
        tmp_path,
        'PREFER_BUILT=1; mapfile -t command < <(build_swift_launch_command "services/mlx-text-worker-swift" "melix-text-worker-swift"); printf "%s\\n" "${command[@]}"',
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(binary_path)]


def test_build_swift_launch_command_reports_missing_built_binary(tmp_path: Path) -> None:
    result = run_script_snippet(
        tmp_path,
        'set +e; PREFER_BUILT=1; build_swift_launch_command "services/control-plane-swift" "melix-control-plane" >/tmp/dev-up-missing.out; status=$?; printf "status=%s\\n" "$status"',
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["status=1"]
    assert "Built Swift product is missing for 'melix-control-plane'" in result.stderr
    assert "Run `make swift-test` or `swift build --package-path" in result.stderr


def test_command_substitution_propagates_missing_built_binary_failure(tmp_path: Path) -> None:
    result = run_script_snippet(
        tmp_path,
        'set +e; PREFER_BUILT=1; command_output="$(build_swift_launch_command "services/control-plane-swift" "melix-control-plane")"; status=$?; printf "status=%s\\n" "$status"',
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["status=1"]
    assert "Built Swift product is missing for 'melix-control-plane'" in result.stderr
