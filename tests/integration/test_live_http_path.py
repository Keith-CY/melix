from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


def test_chat_completions_streams_from_the_live_worker_path(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    socket_path = Path("/tmp") / f"melix-live-{uuid.uuid4().hex[:10]}.sock"
    http_port = reserve_port()

    worker_env = os.environ.copy()
    worker_env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'services/mlx-worker-python'}"

    worker = subprocess.Popen(
        [
            "uv",
            "run",
            "--project",
            os.fspath(repo_root / "services/mlx-worker-python"),
            "python",
            "-m",
            "worker.bootstrap",
            "--socket-path",
            os.fspath(socket_path),
            "--backend-mode",
            "deterministic",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=worker_env,
    )

    control_plane_env = os.environ.copy()
    control_plane_env["MELIX_HTTP_PORT"] = str(http_port)
    control_plane_env["MELIX_WORKER_SOCKET_PATH"] = os.fspath(socket_path)
    control_plane_env["MELIX_REPO_ROOT"] = os.fspath(repo_root)

    control_plane = subprocess.Popen(
        [
            "swift",
            "run",
            "--package-path",
            "services/control-plane-swift",
            "melix-control-plane",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=control_plane_env,
    )

    try:
        wait_for_http_models(http_port, worker=worker, control_plane=control_plane)
        response = urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{http_port}/v1/chat/completions",
                data=json.dumps(
                    {
                        "model": "melix-dev-text",
                        "stream": True,
                        "messages": [{"role": "user", "content": "hello live path"}],
                    }
                ).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )
        body = response.read().decode("utf-8")

        assert response.status == 200
        assert "text/event-stream" in response.headers["Content-Type"]
        assert "\"content\":\"Echo" in body
        assert "data: [DONE]" in body
    finally:
        control_plane.terminate()
        worker.terminate()
        control_plane.wait(timeout=10)
        worker.wait(timeout=10)


def reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_http_models(
    port: int,
    worker: subprocess.Popen[str] | None = None,
    control_plane: subprocess.Popen[str] | None = None,
) -> None:
    deadline = time.time() + 60
    last_error: Exception | None = None

    while time.time() < deadline:
        if worker is not None and worker.poll() is not None:
            stdout, stderr = worker.communicate(timeout=1)
            raise AssertionError(f"Worker exited before warm model was visible: stdout={stdout!r} stderr={stderr!r}")
        if control_plane is not None and control_plane.poll() is not None:
            stdout, stderr = control_plane.communicate(timeout=1)
            raise AssertionError(
                f"Control plane exited before warm model was visible: stdout={stdout!r} stderr={stderr!r}"
            )
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                states = {item["id"]: item["melix_state"] for item in payload["data"]}
                if states.get("melix-dev-text") == "warm":
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.2)

    raise AssertionError(f"Control plane never exposed a warm dev model on port {port}: {last_error}")
