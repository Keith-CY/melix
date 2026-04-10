from __future__ import annotations

import json
import os
import re
import shlex
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
        environment_overrides: dict[str, str] | None = None,
    ) -> None:
        self.repo_root = repo_root
        token = uuid.uuid4().hex[:10]
        self.swift_socket_path = Path("/tmp") / f"melix-swift-{token}.sock"
        self.python_socket_path = Path("/tmp") / f"melix-python-{token}.sock"
        self.control_plane_metrics_path = Path("/tmp") / f"melix-control-plane-{token}.json"
        self.swift_text_worker_metrics_path = Path("/tmp") / f"melix-swift-metrics-{token}.json"
        self.python_worker_metrics_path = Path("/tmp") / f"melix-python-metrics-{token}.json"
        self.runtime_state_root = Path("/tmp") / f"melix-home-{token}"
        self.gateway_config_store_path = self.runtime_state_root / "state" / "gateway-config.json"
        self.gateway_serving_defaults_store_path = (
            self.runtime_state_root / "state" / "gateway-serving-defaults.json"
        )
        self.model_ops_jobs_root = self.runtime_state_root / "jobs" / "model-ops"
        self.evaluation_jobs_root = self.model_ops_jobs_root / "evaluation"
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
        self.environment_overrides = dict(environment_overrides or {})
        self.cleanup_runtime_state_root = "MELIX_HOME" not in self.environment_overrides
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
        self.startup_timings: dict[str, float] = {
            "swift_text_worker_ready_ms": 0.0,
            "python_worker_ready_ms": 0.0,
            "control_plane_spawn_to_ready_ms": 0.0,
        }

    def start(self) -> None:
        self.startup_timings = {
            "swift_text_worker_ready_ms": 0.0,
            "python_worker_ready_ms": 0.0,
            "control_plane_spawn_to_ready_ms": 0.0,
        }
        if self.should_start_swift_text_worker:
            swift_started_at = time.perf_counter()
            swift_text_worker_binary = ensure_swift_product_binary(
                self.repo_root,
                package_path=Path("services/mlx-text-worker-swift"),
                product_name="melix-text-worker-swift",
            )
            swift_env = os.environ.copy()
            swift_env.update(self.environment_overrides)
            swift_env["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = os.fspath(self.swift_socket_path)
            swift_env["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] = self.swift_backend_mode
            swift_env["MELIX_SWIFT_TEXT_WORKER_METRICS_PATH"] = os.fspath(self.swift_text_worker_metrics_path)
            swift_env["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT"] = os.fspath(self.swift_cache_root)
            swift_env["MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS"] = str(time.perf_counter_ns())
            self.swift_text_worker_stdout = self.swift_text_worker_stdout_path.open("w", encoding="utf-8")
            self.swift_text_worker_stderr = self.swift_text_worker_stderr_path.open("w", encoding="utf-8")
            self.swift_text_worker = subprocess.Popen(
                [os.fspath(swift_text_worker_binary)],
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
            self.startup_timings["swift_text_worker_ready_ms"] = (
                time.perf_counter() - swift_started_at
            ) * 1_000.0

        if self.should_start_python_worker:
            python_started_at = time.perf_counter()
            worker_env = os.environ.copy()
            worker_env.update(self.environment_overrides)
            pythonpath_segments: list[str] = []
            pythonpath_prefix = worker_env.get("MELIX_PYTHONPATH_PREFIX", "").strip()
            if pythonpath_prefix:
                pythonpath_segments.append(pythonpath_prefix)
            pythonpath_segments.extend(
                [
                    os.fspath(self.repo_root),
                    os.fspath(self.repo_root / "services/mlx-worker-python"),
                ]
            )
            worker_env["PYTHONPATH"] = os.pathsep.join(pythonpath_segments)
            worker_env["MELIX_PYTHON_WORKER_METRICS_PATH"] = os.fspath(self.python_worker_metrics_path)
            worker_env["MELIX_PYTHON_WORKER_STARTUP_T0_NS"] = str(time.perf_counter_ns())
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
            self.startup_timings["python_worker_ready_ms"] = (
                time.perf_counter() - python_started_at
            ) * 1_000.0

        control_plane_started_at = time.perf_counter()
        control_plane_binary = ensure_swift_product_binary(
            self.repo_root,
            package_path=Path("services/control-plane-swift"),
            product_name="melix-control-plane",
        )
        control_plane_env = os.environ.copy()
        control_plane_env.update(self.environment_overrides)
        if "MELIX_HOME" not in control_plane_env:
            control_plane_env["MELIX_HOME"] = os.fspath(self.runtime_state_root)
        if "MELIX_GATEWAY_CONFIG_STORE_PATH" not in control_plane_env:
            control_plane_env["MELIX_GATEWAY_CONFIG_STORE_PATH"] = os.fspath(self.gateway_config_store_path)
        if "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH" not in control_plane_env:
            control_plane_env["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] = os.fspath(
                self.gateway_serving_defaults_store_path
            )
        control_plane_env.setdefault("MELIX_MODEL_OPS_JOBS_ROOT", os.fspath(self.model_ops_jobs_root))
        control_plane_env.setdefault("MELIX_EVALUATION_JOBS_ROOT", os.fspath(self.evaluation_jobs_root))
        control_plane_env["MELIX_HTTP_PORT"] = str(self.http_port)
        control_plane_env["MELIX_WORKER_SOCKET_PATH"] = os.fspath(self.python_socket_path)
        control_plane_env["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = os.fspath(self.swift_socket_path)
        control_plane_env["MELIX_CONTROL_PLANE_METRICS_PATH"] = os.fspath(self.control_plane_metrics_path)
        control_plane_env["MELIX_REPO_ROOT"] = os.fspath(self.repo_root)
        self.control_plane_stdout = self.control_plane_stdout_path.open("w", encoding="utf-8")
        self.control_plane_stderr = self.control_plane_stderr_path.open("w", encoding="utf-8")

        self.control_plane = subprocess.Popen(
            [os.fspath(control_plane_binary)],
            cwd=self.repo_root,
            stdout=self.control_plane_stdout,
            stderr=self.control_plane_stderr,
            text=True,
            env=control_plane_env,
            start_new_session=True,
        )

        wait_for_http_ready(
            self.http_port,
            request_headers=self._gateway_request_headers(),
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
        self.startup_timings["control_plane_spawn_to_ready_ms"] = (
            time.perf_counter() - control_plane_started_at
        ) * 1_000.0

    def stop(self) -> None:
        self.stop_control_plane()
        self.stop_python_worker()
        self.stop_swift_text_worker()
        if self.cleanup_runtime_state_root:
            self._remove_tree(self.runtime_state_root)

    def stop_python_worker(self) -> None:
        self._stop_process("python worker", self.python_worker)
        self.python_worker = None
        self._close_logs("python_worker")
        self.python_socket_path.unlink(missing_ok=True)
        self.python_worker_metrics_path.unlink(missing_ok=True)

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

    def responses_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/responses"

    def completions_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/completions"

    def messages_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/messages"

    def image_generations_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/images/generations"

    def image_edits_url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}/v1/images/edits"

    def cli_environment(self, repo_root: Path) -> dict[str, str]:
        environment = dict(self.environment_overrides)
        environment.setdefault("MELIX_HOME", os.fspath(self.runtime_state_root))
        environment.setdefault("MELIX_GATEWAY_CONFIG_STORE_PATH", os.fspath(self.gateway_config_store_path))
        environment.setdefault(
            "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH",
            os.fspath(self.gateway_serving_defaults_store_path),
        )
        environment["MELIX_REPO_ROOT"] = os.fspath(repo_root)
        environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] = os.fspath(self.swift_socket_path)
        environment["MELIX_WORKER_SOCKET_PATH"] = os.fspath(self.python_socket_path)
        environment["MELIX_CONTROL_PLANE_METRICS_PATH"] = os.fspath(self.control_plane_metrics_path)
        environment.setdefault("MELIX_MODEL_OPS_JOBS_ROOT", os.fspath(self.model_ops_jobs_root))
        environment.setdefault("MELIX_EVALUATION_JOBS_ROOT", os.fspath(self.evaluation_jobs_root))
        return environment

    def wait_for_models(self, model_ids: list[str], *, timeout_seconds: float = 120) -> None:
        wait_for_http_model_states(
            self.http_port,
            required_states={model_id: "warm" for model_id in model_ids},
            request_headers=self._gateway_request_headers(),
            swift_text_worker=self.swift_text_worker,
            swift_text_worker_stdout_path=self.swift_text_worker_stdout_path,
            swift_text_worker_stderr_path=self.swift_text_worker_stderr_path,
            python_worker=self.python_worker,
            python_worker_stdout_path=self.python_worker_stdout_path,
            python_worker_stderr_path=self.python_worker_stderr_path,
            control_plane=self.control_plane,
            control_plane_stdout_path=self.control_plane_stdout_path,
            control_plane_stderr_path=self.control_plane_stderr_path,
            timeout_seconds=timeout_seconds,
        )

    def _gateway_request_headers(self) -> dict[str, str]:
        auth_mode = self.environment_overrides.get("MELIX_GATEWAY_AUTH_MODE", "").strip().lower()
        if auth_mode == "bearer_token":
            token = self.environment_overrides.get("MELIX_GATEWAY_BEARER_TOKEN", "").strip()
            if token:
                return {"Authorization": f"Bearer {token}"}
            return {}

        if auth_mode == "api_keys" and _parse_bool(self.environment_overrides.get("MELIX_GATEWAY_SHARED_ACCESS_ENABLED")):
            raw_keys = self.environment_overrides.get("MELIX_GATEWAY_API_KEYS_JSON", "").strip()
            if not raw_keys:
                return {}
            try:
                values = json.loads(raw_keys)
            except json.JSONDecodeError:
                return {}
            if not isinstance(values, list):
                return {}
            for value in values:
                if not isinstance(value, dict):
                    continue
                token = str(value.get("token", "")).strip()
                if token:
                    return {"x-api-key": token}
        return {}

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


def resolve_swift_product_binary(
    repo_root: Path,
    *,
    package_path: Path,
    product_name: str,
    configuration: str = "debug",
) -> Path:
    build_root = repo_root / package_path / ".build"
    candidates = [build_root / configuration / product_name]
    candidates.extend(sorted(build_root.glob(f"*/{configuration}/{product_name}")))

    executable_candidates = [
        candidate
        for candidate in candidates
        if candidate.is_file() and os.access(candidate, os.X_OK)
    ]
    if executable_candidates:
        return max(
            executable_candidates,
            key=lambda candidate: (candidate.stat().st_mtime, len(candidate.parts)),
        )

    raise AssertionError(
        "Required Swift product binary is missing. "
        f"Expected a built executable for {product_name!r} under {build_root}. "
        "Run `make swift-test` or `swift build --package-path <package>` before integration tests."
    )


def ensure_swift_product_binary(
    repo_root: Path,
    *,
    package_path: Path,
    product_name: str,
    timeout_seconds: float = 600.0,
    configuration: str = "debug",
) -> Path:
    try:
        return resolve_swift_product_binary(
            repo_root,
            package_path=package_path,
            product_name=product_name,
            configuration=configuration,
        )
    except AssertionError as error:
        swift_home = repo_root / ".swift-home"
        clang_module_cache_path = repo_root / ".build" / "ModuleCache.noindex"
        swift_home.mkdir(parents=True, exist_ok=True)
        clang_module_cache_path.mkdir(parents=True, exist_ok=True)

        build_environment = os.environ.copy()
        build_environment["HOME"] = os.fspath(swift_home)
        build_environment["CLANG_MODULE_CACHE_PATH"] = os.fspath(clang_module_cache_path)
        build_command = [
            "swift",
            "build",
        ]
        if configuration == "release":
            build_command.extend(["-c", "release"])
        build_command.extend(
            [
                "--package-path",
                os.fspath(repo_root / package_path),
                "--product",
                product_name,
            ]
        )
        result = subprocess.run(
            build_command,
            cwd=repo_root,
            env=build_environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            raise AssertionError(
                "Unable to build required Swift product "
                f"{product_name!r} under {repo_root / package_path}. "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            ) from error
        return resolve_swift_product_binary(
            repo_root,
            package_path=package_path,
            product_name=product_name,
            configuration=configuration,
        )


def resolve_cli_binary(repo_root: Path, *, configuration: str = "debug") -> Path:
    return resolve_swift_product_binary(
        repo_root,
        package_path=Path("."),
        product_name="melix",
        configuration=configuration,
    )


def ensure_cli_binary(
    repo_root: Path,
    *,
    timeout_seconds: float = 600.0,
    configuration: str = "debug",
) -> Path:
    return ensure_swift_product_binary(
        repo_root,
        package_path=Path("."),
        product_name="melix",
        timeout_seconds=timeout_seconds,
        configuration=configuration,
    )


def run_melix_cli(
    repo_root: Path,
    args: list[str],
    environment: dict[str, str],
    *,
    configuration: str = "debug",
    timeout_seconds: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    cli_binary = ensure_cli_binary(
        repo_root,
        timeout_seconds=timeout_seconds,
        configuration=configuration,
    )
    merged_environment = os.environ.copy()
    merged_environment.update(environment)
    return subprocess.run(
        [os.fspath(cli_binary), *args],
        cwd=repo_root,
        env=merged_environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def run_phase1_canonical_cli(
    repo_root: Path,
    environment: dict[str, str],
    *,
    case_id: str,
    configuration: str = "release",
    timeout_seconds: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    cases = _phase1_canonical_cli_cases(repo_root)
    try:
        args = cases[case_id]
    except KeyError as error:
        raise AssertionError(f"Unknown Phase 1 canonical CLI case: {case_id}") from error
    return run_melix_cli(
        repo_root,
        args,
        environment,
        configuration=configuration,
        timeout_seconds=timeout_seconds,
    )


def _phase1_canonical_cli_cases(repo_root: Path) -> dict[str, list[str]]:
    runbook_path = repo_root / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_text = runbook_path.read_text(encoding="utf-8")
    section_marker = "## Phase 1 Canonical CLI Acceptance Suite"
    if section_marker not in runbook_text:
        raise AssertionError(f"Unable to locate {section_marker!r} in {runbook_path}.")
    section = runbook_text.split(section_marker, 1)[1]
    next_heading = re.search(r"^##\s+", section, flags=re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]

    prerequisite_match = re.search(r"Prerequisite:.*?```bash\n(.*?)```", section, flags=re.DOTALL)
    positive_match = re.search(
        r"Use the release build to run the positive acceptance suite.*?```bash\n(.*?)```",
        section,
        flags=re.DOTALL,
    )
    negative_match = re.search(
        r"Use these negative acceptance commands.*?```bash\n(.*?)```",
        section,
        flags=re.DOTALL,
    )
    if prerequisite_match is None or positive_match is None or negative_match is None:
        raise AssertionError(
            "Expected Phase 1 canonical CLI section to contain prerequisite, positive, and negative bash blocks."
        )

    commands: dict[str, list[str]] = {}
    positive_block = positive_match.group(1)
    negative_block = negative_match.group(1)

    for raw_line in positive_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = shlex.split(line)
        if not tokens or not tokens[0].endswith("melix"):
            continue
        args = tokens[1:]
        if args[:2] == ["bench", "run"]:
            commands["bench_run_positive"] = args
        elif args[:3] == ["bench", "matrix", "run"]:
            commands["bench_matrix_run_positive"] = args
        elif args[:2] == ["eval", "run"]:
            commands["eval_run_positive"] = args

    for raw_line in negative_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = shlex.split(line)
        if not tokens or not tokens[0].endswith("melix"):
            continue
        args = tokens[1:]
        if args[:3] == ["bench", "matrix", "run"] and "--duration-seconds" in args:
            commands["bench_matrix_conflicting_load_budget_negative"] = args
        elif args[:2] == ["eval", "run"]:
            commands["eval_run_unsupported_repo_negative"] = args

    required_cases = {
        "bench_run_positive",
        "bench_matrix_run_positive",
        "eval_run_positive",
        "bench_matrix_conflicting_load_budget_negative",
        "eval_run_unsupported_repo_negative",
    }
    missing_cases = sorted(required_cases.difference(commands))
    if missing_cases:
        raise AssertionError(
            "Phase 1 canonical CLI cases are missing from the runbook: "
            + ", ".join(missing_cases)
        )
    return commands


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
    wait_for_http_model_states(
        port,
        required_states={"melix-dev-text": "warm"},
        swift_text_worker=swift_text_worker,
        swift_text_worker_stdout_path=swift_text_worker_stdout_path,
        swift_text_worker_stderr_path=swift_text_worker_stderr_path,
        python_worker=python_worker,
        python_worker_stdout_path=python_worker_stdout_path,
        python_worker_stderr_path=python_worker_stderr_path,
        control_plane=control_plane,
        control_plane_stdout_path=control_plane_stdout_path,
        control_plane_stderr_path=control_plane_stderr_path,
        timeout_seconds=timeout_seconds,
    )


def wait_for_http_ready(
    port: int,
    request_headers: dict[str, str] | None = None,
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
    wait_for_http_model_states(
        port,
        required_states={},
        request_headers=request_headers,
        swift_text_worker=swift_text_worker,
        swift_text_worker_stdout_path=swift_text_worker_stdout_path,
        swift_text_worker_stderr_path=swift_text_worker_stderr_path,
        python_worker=python_worker,
        python_worker_stdout_path=python_worker_stdout_path,
        python_worker_stderr_path=python_worker_stderr_path,
        control_plane=control_plane,
        control_plane_stdout_path=control_plane_stdout_path,
        control_plane_stderr_path=control_plane_stderr_path,
        timeout_seconds=timeout_seconds,
    )


def wait_for_http_model_states(
    port: int,
    *,
    required_states: dict[str, str],
    request_headers: dict[str, str] | None = None,
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
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/models",
                headers=request_headers or {},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                states = {item["id"]: item["melix_state"] for item in payload["data"]}
                if all(
                    _model_state_satisfies(states.get(model_id), expected)
                    for model_id, expected in required_states.items()
                ):
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.2)

    raise AssertionError(
        "Control plane never exposed the required model states "
        f"{required_states} on port {port} within {timeout_seconds:.1f}s: {last_error}"
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


def _model_state_satisfies(actual: str | None, expected: str) -> bool:
    if expected == "warm":
        return actual in {"warm", "pinned"}
    return actual == expected


def _parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
