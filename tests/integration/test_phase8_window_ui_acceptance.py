from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from tests.integration.helpers import LiveMelixStack
from tests.integration.test_phase8_cli_acceptance import build_cli_binary
from tests.integration.test_phase8_cli_acceptance import write_local_model_fixture


@lru_cache(maxsize=1)
def build_menubar_binary(repo_root: Path) -> Path:
    subprocess.run(
        ["swift", "build", "--package-path", "apps/macos-menubar", "--product", "melix-menubar"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_root / "apps/macos-menubar/.build/arm64-apple-macosx/debug/melix-menubar"


def run_window_ui_acceptance(
    repo_root: Path,
    *,
    env_overrides: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [str(build_menubar_binary(repo_root))],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def test_window_ui_acceptance_writes_bundle_and_screenshot(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = tmp_path / "melix-home"
    cli_bundle_path = melix_home / "acceptance" / "phase8" / "cli" / "2026-04-09T162920Z" / "bundle.json"
    cli_bundle_path.parent.mkdir(parents=True, exist_ok=True)
    cli_bundle_path.write_text('{"surface":"cli"}\n', encoding="utf-8")

    fixture_model = tmp_path / "fixture-model"
    write_local_model_fixture(fixture_model)

    stack = LiveMelixStack(repo_root, environment_overrides={"MELIX_HOME": str(melix_home)})
    stack.start()
    try:
        completed = run_window_ui_acceptance(
            repo_root,
            env_overrides={
                "MELIX_HOME": str(melix_home),
                "MELIX_REPO_ROOT": str(repo_root),
                "MELIX_CLI": str(build_cli_binary(repo_root)),
                "MELIX_WORKER_SOCKET_PATH": str(stack.python_socket_path),
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(stack.swift_socket_path),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE": "1",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP": "2026-04-09T120000Z",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID": "melix-dev-qwen-local",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH": str(fixture_model),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH": str(cli_bundle_path),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES": "smoke",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES": "smoke",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES": "mmlu",
            },
        )
    finally:
        stack.stop()

    payload = json.loads(completed.stdout)
    bundle_path = Path(payload["bundle_path"])
    screenshot_path = Path(payload["screenshot_path"])
    assert bundle_path.is_file()
    assert screenshot_path.is_file()

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["cli_evidence_bundle_path"] == str(cli_bundle_path)
    assert bundle["screenshot_path"] == str(screenshot_path)


def test_window_ui_acceptance_rejects_missing_cli_bundle_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = tmp_path / "melix-home"
    fixture_model = tmp_path / "fixture-model"
    write_local_model_fixture(fixture_model)

    stack = LiveMelixStack(repo_root, environment_overrides={"MELIX_HOME": str(melix_home)})
    stack.start()
    try:
        completed = run_window_ui_acceptance(
            repo_root,
            check=False,
            env_overrides={
                "MELIX_HOME": str(melix_home),
                "MELIX_REPO_ROOT": str(repo_root),
                "MELIX_CLI": str(build_cli_binary(repo_root)),
                "MELIX_WORKER_SOCKET_PATH": str(stack.python_socket_path),
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(stack.swift_socket_path),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE": "1",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP": "2026-04-09T120000Z",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID": "melix-dev-qwen-local",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH": str(fixture_model),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH": str(tmp_path / "missing-cli-bundle.json"),
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES": "smoke",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES": "smoke",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES": "mmlu",
            },
        )
    finally:
        stack.stop()

    assert completed.returncode != 0
    assert "cli evidence bundle" in completed.stderr.lower()
