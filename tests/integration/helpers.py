from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    cache_pb2,
    cache_pb2_grpc,
    inference_pb2,
    inference_pb2_grpc,
    runtime_pb2,
    runtime_pb2_grpc,
)


class LiveMelixStack:
    def __init__(
        self,
        repo_root: Path,
        *,
        swift_backend_mode: str = "deterministic",
        python_backend_mode: str = "deterministic",
        start_swift_text_worker: bool = True,
        start_python_worker: bool = True,
        swift_cache_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root
        token = uuid.uuid4().hex[:10]
        self.swift_socket_path = Path("/tmp") / f"melix-swift-{token}.sock"
        self.python_socket_path = Path("/tmp") / f"melix-python-{token}.sock"
        self.control_plane_metrics_path = Path("/tmp") / f"melix-control-plane-{token}.json"
        self.swift_text_worker_metrics_path = Path("/tmp") / f"melix-swift-metrics-{token}.json"
        self.http_port = reserve_port()
        self.swift_text_worker_stdout_path = Path("/tmp") / f"melix-swift-worker-{token}.stdout.log"
        self.swift_text_worker_stderr_path = Path("/tmp") / f"melix-swift-worker-{token}.stderr.log"
        self.python_worker_stdout_path = Path("/tmp") / f"melix-python-worker-{token}.stdout.log"
        self.python_worker_stderr_path = Path("/tmp") / f"melix-python-worker-{token}.stderr.log"
        self.control_plane_stdout_path = Path("/tmp") / f"melix-control-plane-{token}.stdout.log"
        self.control_plane_stderr_path = Path("/tmp") / f"melix-control-plane-{token}.stderr.log"
        self.swift_cache_root = swift_cache_root or (Path("/tmp") / f"melix-swift-cache-{token}")
        self.cleanup_swift_cache_root = swift_cache_root is None
        self.swift_backend_mode = swift_backend_mode
        self.python_backend_mode = python_backend_mode
        self.should_start_swift_text_worker = start_swift_text_worker
        self.should_start_python_worker = start_python_worker
        self.swift_text_worker: subprocess.Popen[str] | None = None
        self.python_worker: subprocess.Popen[str] | None = None
        self.control_plane: subprocess.Popen[str] | None = None
        self.swift_text_worker_stdout = None
        self.swift_text_worker_stderr = None
        self.python_worker_stdout = None
        self.python_worker_stderr = None
        self.control_plane_stdout = None
        self.control_plane_stderr = None

    def start(self) -> None:
        if self.should_start_swift_text_worker:
            swift_env = os.environ.copy()
            swift_env["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = os.fspath(self.swift_socket_path)
            swift_env["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] = self.swift_backend_mode
            swift_env["MELIX_SWIFT_TEXT_WORKER_METRICS_PATH"] = os.fspath(self.swift_text_worker_metrics_path)
            swift_env["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT"] = os.fspath(self.swift_cache_root)
            self.swift_text_worker_stdout = self.swift_text_worker_stdout_path.open("w", encoding="utf-8")
            self.swift_text_worker_stderr = self.swift_text_worker_stderr_path.open("w", encoding="utf-8")
            self.swift_text_worker = subprocess.Popen(
                [
                    "swift",
                    "run",
                    "--package-path",
                    "services/mlx-text-worker-swift",
                    "melix-text-worker-swift",
                ],
                cwd=self.repo_root,
                stdout=self.swift_text_worker_stdout,
                stderr=self.swift_text_worker_stderr,
                text=True,
                env=swift_env,
                start_new_session=True,
            )
            wait_for_worker_handshake(
                self.swift_socket_path,
                worker=self.swift_text_worker,
                stdout_path=self.swift_text_worker_stdout_path,
                stderr_path=self.swift_text_worker_stderr_path,
                timeout_seconds=120,
            )

        if self.should_start_python_worker:
            worker_env = os.environ.copy()
            worker_env["PYTHONPATH"] = f"{self.repo_root}:{self.repo_root / 'services/mlx-worker-python'}"
            self.python_worker_stdout = self.python_worker_stdout_path.open("w", encoding="utf-8")
            self.python_worker_stderr = self.python_worker_stderr_path.open("w", encoding="utf-8")

            self.python_worker = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "--project",
                    os.fspath(self.repo_root / "services/mlx-worker-python"),
                    "python",
                    "-m",
                    "worker.bootstrap",
                    "--socket-path",
                    os.fspath(self.python_socket_path),
                    "--backend-mode",
                    self.python_backend_mode,
                ],
                cwd=self.repo_root,
                stdout=self.python_worker_stdout,
                stderr=self.python_worker_stderr,
                text=True,
                env=worker_env,
                start_new_session=True,
            )
            wait_for_worker_handshake(
                self.python_socket_path,
                worker=self.python_worker,
                stdout_path=self.python_worker_stdout_path,
                stderr_path=self.python_worker_stderr_path,
                timeout_seconds=60,
            )

        control_plane_env = os.environ.copy()
        control_plane_env["MELIX_HTTP_PORT"] = str(self.http_port)
        control_plane_env["MELIX_WORKER_SOCKET_PATH"] = os.fspath(self.python_socket_path)
        control_plane_env["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = os.fspath(self.swift_socket_path)
        control_plane_env["MELIX_CONTROL_PLANE_METRICS_PATH"] = os.fspath(self.control_plane_metrics_path)
        control_plane_env["MELIX_REPO_ROOT"] = os.fspath(self.repo_root)
        self.control_plane_stdout = self.control_plane_stdout_path.open("w", encoding="utf-8")
        self.control_plane_stderr = self.control_plane_stderr_path.open("w", encoding="utf-8")

        self.control_plane = subprocess.Popen(
            [
                "swift",
                "run",
                "--package-path",
                "services/control-plane-swift",
                "melix-control-plane",
            ],
            cwd=self.repo_root,
            stdout=self.control_plane_stdout,
            stderr=self.control_plane_stderr,
            text=True,
            env=control_plane_env,
            start_new_session=True,
        )

        wait_for_http_models(
            self.http_port,
            swift_text_worker=self.swift_text_worker,
            swift_text_worker_stdout_path=self.swift_text_worker_stdout_path,
            swift_text_worker_stderr_path=self.swift_text_worker_stderr_path,
            python_worker=self.python_worker,
            python_worker_stdout_path=self.python_worker_stdout_path,
            python_worker_stderr_path=self.python_worker_stderr_path,
            control_plane=self.control_plane,
            control_plane_stdout_path=self.control_plane_stdout_path,
            control_plane_stderr_path=self.control_plane_stderr_path,
            timeout_seconds=120,
        )

    def stop(self) -> None:
        self.stop_control_plane()
        self.stop_python_worker()
        self.stop_swift_text_worker()

    def stop_python_worker(self) -> None:
        self._stop_process("python worker", self.python_worker)
        self.python_worker = None
        self._close_logs("python_worker")
        self.python_socket_path.unlink(missing_ok=True)

    def stop_swift_text_worker(self) -> None:
        self._stop_process("swift text worker", self.swift_text_worker)
        self.swift_text_worker = None
        self._close_logs("swift_text_worker")
        self.swift_socket_path.unlink(missing_ok=True)
        self.swift_text_worker_metrics_path.unlink(missing_ok=True)
        if self.cleanup_swift_cache_root:
            self._remove_tree(self.swift_cache_root)

    def stop_control_plane(self) -> None:
        self._stop_process("control plane", self.control_plane)
        self.control_plane = None
        self._close_logs("control_plane")
        self.control_plane_metrics_path.unlink(missing_ok=True)

    def models_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/models"

    def chat_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/chat/completions"

    def _stop_process(self, name: str, process: subprocess.Popen[str] | None) -> None:
        if process is None:
            return
        if process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait(timeout=10)
        else:
            process.wait(timeout=10)

    def _close_logs(self, prefix: str) -> None:
        for suffix in ("stdout", "stderr"):
            handle = getattr(self, f"{prefix}_{suffix}", None)
            if handle is not None:
                handle.close()
                setattr(self, f"{prefix}_{suffix}", None)
            path = getattr(self, f"{prefix}_{suffix}_path", None)
            if isinstance(path, Path):
                path.unlink(missing_ok=True)

    def _remove_tree(self, root: Path) -> None:
        if not root.exists():
            return
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            else:
                child.rmdir()
        root.rmdir()


def reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_worker_handshake(
    socket_path: Path,
    *,
    worker: subprocess.Popen[str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    timeout_seconds: float = 120,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    channel = grpc.insecure_channel(f"unix://{socket_path}")
    stub = runtime_pb2_grpc.RuntimeServiceStub(channel)

    try:
        while time.time() < deadline:
            if worker is not None and worker.poll() is not None:
                raise AssertionError(_format_process_failure("Worker exited before handshake completed", stdout_path, stderr_path))
            try:
                request = runtime_pb2.HandshakeRequest(
                    protocol_version="melix.worker.v1",
                    worker_id="integration-tests",
                    controlplane_instance_id="integration-tests",
                )
                response = stub.Handshake(request, timeout=2)
                if response.protocol_version == "melix.worker.v1":
                    return
            except grpc.RpcError as exc:
                last_error = exc
            time.sleep(0.2)
    finally:
        channel.close()

    raise AssertionError(f"Worker never became ready on socket {socket_path}: {last_error}")


def wait_for_http_models(
    port: int,
    swift_text_worker: subprocess.Popen[str] | None = None,
    swift_text_worker_stdout_path: Path | None = None,
    swift_text_worker_stderr_path: Path | None = None,
    python_worker: subprocess.Popen[str] | None = None,
    python_worker_stdout_path: Path | None = None,
    python_worker_stderr_path: Path | None = None,
    control_plane: subprocess.Popen[str] | None = None,
    control_plane_stdout_path: Path | None = None,
    control_plane_stderr_path: Path | None = None,
    timeout_seconds: float = 120,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        if swift_text_worker is not None and swift_text_worker.poll() is not None:
            raise AssertionError(
                _format_process_failure(
                    "Swift text worker exited before warm model was visible",
                    swift_text_worker_stdout_path,
                    swift_text_worker_stderr_path,
                )
            )
        if python_worker is not None and python_worker.poll() is not None:
            raise AssertionError(
                _format_process_failure(
                    "Python worker exited before warm model was visible",
                    python_worker_stdout_path,
                    python_worker_stderr_path,
                )
            )
        if control_plane is not None and control_plane.poll() is not None:
            raise AssertionError(
                _format_process_failure(
                    "Control plane exited before warm model was visible",
                    control_plane_stdout_path,
                    control_plane_stderr_path,
                )
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

    raise AssertionError(
        f"Control plane never exposed a warm dev model on port {port} within {timeout_seconds:.1f}s: {last_error}"
    )


def abort_worker_request(socket_path: Path, request_id: str) -> bool:
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = inference_pb2_grpc.InferenceServiceStub(channel)
        response = stub.Abort(inference_pb2.AbortRequest(request_id=request_id), timeout=5)
        return bool(response.ok and response.found)
    finally:
        channel.close()


def get_cache_stats(socket_path: Path) -> cache_pb2.GetCacheStatsResponse:
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    try:
        stub = cache_pb2_grpc.CacheServiceStub(channel)
        return stub.GetCacheStats(cache_pb2.GetCacheStatsRequest(), timeout=5)
    finally:
        channel.close()


def read_metrics_export(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_process_failure(message: str, stdout_path: Path | None, stderr_path: Path | None) -> str:
    stdout = stdout_path.read_text(encoding="utf-8") if isinstance(stdout_path, Path) and stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8") if isinstance(stderr_path, Path) and stderr_path.exists() else ""
    return f"{message}: stdout={stdout!r} stderr={stderr!r}"
