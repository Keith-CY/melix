from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
from functools import lru_cache
from pathlib import Path
import uuid

from tests.integration.helpers import LiveMelixStack
from tests.integration.helpers import wait_for_worker_handshake


@lru_cache(maxsize=1)
def build_cli_binary(repo_root: Path) -> Path:
    subprocess.run(
        ["swift", "build", "--product", "melix"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_root / ".build" / "arm64-apple-macosx" / "debug" / "melix"


def run_cli(
    repo_root: Path,
    args: list[str],
    *,
    env_overrides: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides)
    env["MELIX_REPO_ROOT"] = str(repo_root)
    binary = build_cli_binary(repo_root)
    return subprocess.run(
        [str(binary), *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def run_cli_json(repo_root: Path, args: list[str], *, env_overrides: dict[str, str]) -> object:
    completed = run_cli(repo_root, args, env_overrides=env_overrides)
    return json.loads(completed.stdout)


def write_local_model_fixture(model_root: Path) -> None:
    model_root.mkdir(parents=True, exist_ok=True)
    (model_root / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (model_root / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (model_root / "model.safetensors").write_bytes(b"weights")


@contextlib.contextmanager
def running_python_model_ops_worker(
    repo_root: Path,
    *,
    environment_overrides: dict[str, str],
) -> Path:
    token = uuid.uuid4().hex[:10]
    socket_path = Path("/tmp") / f"melix-phase8-python-{token}.sock"
    stdout_path = Path("/tmp") / f"melix-phase8-python-{token}.stdout.log"
    stderr_path = Path("/tmp") / f"melix-phase8-python-{token}.stderr.log"
    env = os.environ.copy()
    env.update(environment_overrides)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(repo_root),
            str(repo_root / "services/mlx-worker-python"),
        ]
    )
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "services/mlx-worker-python"),
            "--extra",
            "mlx",
            "python",
            "-m",
            "worker.bootstrap",
            "--socket-path",
            str(socket_path),
            "--backend-mode",
            "deterministic",
        ],
        cwd=repo_root,
        stdout=stdout,
        stderr=stderr,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        wait_for_worker_handshake(
            socket_path,
            worker=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=60,
        )
        yield socket_path
    finally:
        if process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait(timeout=10)
        stdout.close()
        stderr.close()
        socket_path.unlink(missing_ok=True)
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)


def test_cli_materialization_closes_local_import_receipts_and_registry_visibility(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "fixture-model"
    melix_home = tmp_path / "melix-home"
    managed_root = tmp_path / "managed-models"
    write_local_model_fixture(source_dir)
    with running_python_model_ops_worker(
        repo_root,
        environment_overrides={
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        },
    ) as python_socket_path:
        env = {
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            "MELIX_WORKER_SOCKET_PATH": str(python_socket_path),
        }

        receipt = run_cli_json(
            repo_root,
            [
                "model",
                "import",
                "--path",
                str(source_dir),
                "--model-id",
                "melix-dev-qwen-local",
                "--model-kind",
                "text",
                "--revision",
                "main",
                "--json",
            ],
            env_overrides=env,
        )
        assert receipt["model_id"] == "melix-dev-qwen-local"
        assert receipt["source_kind"] == "local_path"
        assert receipt["source_locator"] == str(source_dir.resolve())
        assert Path(receipt["managed_model_path"]).is_dir()

        models = run_cli_json(
            repo_root,
            [
                "model",
                "list",
                "--json",
            ],
            env_overrides=env,
        )
        assert any(model["model_id"] == "melix-dev-qwen-local" for model in models)


def test_cli_local_import_rejects_missing_source_directory(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = tmp_path / "melix-home"
    managed_root = tmp_path / "managed-models"
    with running_python_model_ops_worker(
        repo_root,
        environment_overrides={
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        },
    ) as python_socket_path:
        env = {
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            "MELIX_WORKER_SOCKET_PATH": str(python_socket_path),
        }

        completed = run_cli(
            repo_root,
            [
                "model",
                "import",
                "--path",
                str(tmp_path / "missing-model"),
                "--model-id",
                "melix-dev-qwen-local",
                "--json",
            ],
            env_overrides=env,
            check=False,
        )

        assert completed.returncode != 0
        assert "existing source directory" in completed.stderr


def test_cli_chat_run_rejects_missing_message_argument(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    melix_home = tmp_path / "melix-home"
    managed_root = tmp_path / "managed-models"
    env = {
        "MELIX_HOME": str(melix_home),
        "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
    }

    completed = run_cli(
        repo_root,
        [
            "chat",
            "run",
            "--model-id",
            "melix-dev-qwen-local",
        ],
        env_overrides=env,
        check=False,
    )

    assert completed.returncode != 0
    assert "--message is required for melix chat run." in completed.stderr


def test_cli_chat_run_rebinds_primary_session_without_dev_text_model_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "fixture-model"
    melix_home = tmp_path / "melix-home"
    managed_root = tmp_path / "managed-models"
    write_local_model_fixture(source_dir)

    stack = LiveMelixStack(
        repo_root,
        environment_overrides={
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        },
    )
    stack.start()
    try:
        env = {
            "MELIX_HOME": str(melix_home),
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            "MELIX_WORKER_SOCKET_PATH": str(stack.python_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(stack.swift_socket_path),
        }
        assert "MELIX_DEV_TEXT_MODEL_PATH" not in env

        receipt = run_cli_json(
            repo_root,
            [
                "model",
                "import",
                "--path",
                str(source_dir),
                "--model-id",
                "melix-dev-qwen-local",
                "--model-kind",
                "text",
                "--revision",
                "main",
                "--json",
            ],
            env_overrides=env,
        )

        created_state = run_cli_json(
            repo_root,
            [
                "server",
                "session",
                "create",
                "--title",
                "Primary Session",
                "--model-id",
                "melix-dev-text",
                "--json",
            ],
            env_overrides=env,
        )
        assert created_state["server_sessions"][0]["id"] == "server-session-1"

        run_cli_json(
            repo_root,
            [
                "model",
                "roots",
                "rescan",
                "--json",
            ],
            env_overrides=env,
        )
        run_cli_json(
            repo_root,
            [
                "server",
                "session",
                "update",
                "--server-session-id",
                "server-session-1",
                "--model-id",
                receipt["model_id"],
                "--json",
            ],
            env_overrides=env,
        )
        selected_state = run_cli_json(
            repo_root,
            [
                "server",
                "session",
                "select",
                "--server-session-id",
                "server-session-1",
                "--json",
            ],
            env_overrides=env,
        )
        assert selected_state["selected_server_session_id"] == "server-session-1"

        snapshot = run_cli_json(
            repo_root,
            [
                "server",
                "start",
                "--server-session-id",
                "server-session-1",
                "--json",
            ],
            env_overrides=env,
        )
        assert snapshot["server_state"] == "server_ready"

        chat_receipt = run_cli_json(
            repo_root,
            [
                "chat",
                "run",
                "--model-id",
                receipt["model_id"],
                "--message",
                "Reply with BASE_OK",
                "--server-session-id",
                "server-session-1",
                "--json",
            ],
            env_overrides=env,
        )
        assert chat_receipt["model_id"] == receipt["model_id"]
        assert chat_receipt["server_session_id"] == "server-session-1"
        assert chat_receipt["finish_reason"] == "stop"
        assert chat_receipt["assistant_text"] == "Echo: Reply with BASE_OK"
        assert chat_receipt["request_id"]
    finally:
        stack.stop()
