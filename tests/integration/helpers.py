from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import inference_pb2, inference_pb2_grpc


class LiveMelixStack:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.socket_path = Path("/tmp") / f"melix-live-{uuid.uuid4().hex[:10]}.sock"
        self.http_port = reserve_port()
        self.worker: subprocess.Popen[str] | None = None
        self.control_plane: subprocess.Popen[str] | None = None

    def start(self) -> None:
        worker_env = os.environ.copy()
        worker_env["PYTHONPATH"] = f"{self.repo_root}:{self.repo_root / 'services/mlx-worker-python'}"

        self.worker = subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                os.fspath(self.repo_root / "services/mlx-worker-python"),
                "python",
                "-m",
                "worker.bootstrap",
                "--socket-path",
                os.fspath(self.socket_path),
                "--backend-mode",
                "deterministic",
            ],
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=worker_env,
        )

        control_plane_env = os.environ.copy()
        control_plane_env["MELIX_HTTP_PORT"] = str(self.http_port)
        control_plane_env["MELIX_WORKER_SOCKET_PATH"] = os.fspath(self.socket_path)
        control_plane_env["MELIX_REPO_ROOT"] = os.fspath(self.repo_root)

        self.control_plane = subprocess.Popen(
            [
                "swift",
                "run",
                "--package-path",
                "services/control-plane-swift",
                "melix-control-plane",
            ],
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=control_plane_env,
        )

        wait_for_http_models(self.http_port, worker=self.worker, control_plane=self.control_plane)

    def stop(self) -> None:
        for process in (self.control_plane, self.worker):
            if process is None:
                continue
            process.terminate()
        for process in (self.control_plane, self.worker):
            if process is None:
                continue
            process.wait(timeout=10)

    def models_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/models"

    def chat_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/chat/completions"


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


def abort_worker_request(socket_path: Path, request_id: str) -> bool:
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = inference_pb2_grpc.InferenceServiceStub(channel)
        response = stub.Abort(inference_pb2.AbortRequest(request_id=request_id), timeout=5)
        return bool(response.ok and response.found)
    finally:
        channel.close()
