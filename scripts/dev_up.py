#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USAGE_TEXT = """Usage: bash scripts/dev_up.sh [--prefer-built]

Options:
  --prefer-built  Start Swift processes from existing built executables under .build/debug when available.
                  This keeps the Python worker on uv run and fails fast if the required Swift binaries are missing."""


@dataclass(frozen=True)
class DevUpOptions:
    prefer_built: bool = False


@dataclass(frozen=True)
class RuntimeLayout:
    service_instance_name: str
    runtime_dir: Path
    python_socket_path: Path
    swift_text_worker_socket_path: Path
    managed_models_dir: Path
    audio_runtime_packs_dir: Path
    model_ops_jobs_root: Path
    evaluation_jobs_root: Path
    control_plane_metrics_path: Path
    swift_text_worker_metrics_path: Path
    python_worker_metrics_path: Path
    http_port: str
    python_backend_mode: str
    swift_text_worker_backend_mode: str
    uv_cache_dir: Path
    swift_home: Path
    clang_module_cache_path: Path


def print_usage(*, stream) -> None:
    print(USAGE_TEXT, file=stream)


def parse_args(argv: list[str]) -> DevUpOptions:
    prefer_built = False
    for argument in argv:
        if argument == "--prefer-built":
            prefer_built = True
        elif argument in {"-h", "--help"}:
            print_usage(stream=sys.stdout)
            raise SystemExit(0)
        else:
            print(f"Unknown argument: {argument}", file=sys.stderr)
            print_usage(stream=sys.stderr)
            raise SystemExit(2)
    return DevUpOptions(prefer_built=prefer_built)


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def resolve_built_swift_product_binary(repo_root: Path, *, package_path: str, product_name: str) -> Path:
    build_root = repo_root / package_path / ".build"
    candidates = [build_root / "debug" / product_name]
    candidates.extend(sorted(build_root.glob(f"*/debug/{product_name}")))

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise RuntimeError(
        f"Built Swift product is missing for '{product_name}' under {build_root}.\n"
        f"Run `make swift-test` or `swift build --package-path {repo_root / package_path}` before using --prefer-built."
    )


def build_swift_launch_command(
    repo_root: Path,
    *,
    package_path: str,
    product_name: str,
    prefer_built: bool,
) -> list[str]:
    if prefer_built:
        return [os.fspath(resolve_built_swift_product_binary(repo_root, package_path=package_path, product_name=product_name))]
    return [
        "swift",
        "run",
        "--package-path",
        os.fspath(repo_root / package_path),
        product_name,
    ]


def compute_runtime_layout(repo_root: Path) -> RuntimeLayout:
    service_instance_name = _normalize_service_instance_name(os.environ.get("MELIX_SERVICE_INSTANCE_NAME", ""))
    default_runtime_dir = repo_root / ".runtime" / "phase1"
    if service_instance_name:
        default_runtime_dir = repo_root / ".runtime" / "sidecars" / service_instance_name
    runtime_dir = resolve_path(os.environ.get("MELIX_RUNTIME_DIR", default_runtime_dir))
    model_ops_jobs_root = Path(
        os.environ.get("MELIX_MODEL_OPS_JOBS_ROOT", runtime_dir / "jobs" / "model-ops")
    ).expanduser()
    return RuntimeLayout(
        service_instance_name=service_instance_name,
        runtime_dir=runtime_dir,
        python_socket_path=Path(os.environ.get("MELIX_WORKER_SOCKET_PATH", runtime_dir / "python-worker.sock")).expanduser(),
        swift_text_worker_socket_path=Path(
            os.environ.get("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", runtime_dir / "swift-text-worker.sock")
        ).expanduser(),
        managed_models_dir=Path(
            os.environ.get("MELIX_MANAGED_MODEL_ROOT", runtime_dir / "models" / "default-managed")
        ).expanduser(),
        audio_runtime_packs_dir=Path(
            os.environ.get("MELIX_AUDIO_RUNTIME_PACK_ROOT", runtime_dir / "runtime-packs" / "audio")
        ).expanduser(),
        model_ops_jobs_root=model_ops_jobs_root,
        evaluation_jobs_root=Path(
            os.environ.get("MELIX_EVALUATION_JOBS_ROOT", model_ops_jobs_root / "evaluation")
        ).expanduser(),
        control_plane_metrics_path=Path(
            os.environ.get("MELIX_CONTROL_PLANE_METRICS_PATH", runtime_dir / "control-plane-metrics.json")
        ).expanduser(),
        swift_text_worker_metrics_path=Path(
            os.environ.get("MELIX_SWIFT_TEXT_WORKER_METRICS_PATH", runtime_dir / "swift-text-worker-metrics.json")
        ).expanduser(),
        python_worker_metrics_path=Path(
            os.environ.get("MELIX_PYTHON_WORKER_METRICS_PATH", runtime_dir / "python-worker-metrics.json")
        ).expanduser(),
        http_port=os.environ.get("MELIX_HTTP_PORT", "11434"),
        python_backend_mode=os.environ.get("MELIX_BACKEND_MODE", "deterministic"),
        swift_text_worker_backend_mode=os.environ.get("MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "deterministic"),
        uv_cache_dir=resolve_path(os.environ.get("UV_CACHE_DIR", repo_root / ".uv-cache")),
        swift_home=resolve_path(os.environ.get("MELIX_SWIFT_HOME", repo_root / ".swift-home")),
        clang_module_cache_path=resolve_path(
            os.environ.get("MELIX_CLANG_MODULE_CACHE_PATH", repo_root / ".build" / "ModuleCache.noindex")
        ),
    )


def ensure_runtime_directories(layout: RuntimeLayout) -> None:
    for directory in (
        layout.runtime_dir,
        layout.uv_cache_dir,
        layout.swift_home,
        layout.clang_module_cache_path,
        layout.managed_models_dir,
        layout.audio_runtime_packs_dir,
        layout.model_ops_jobs_root,
        layout.evaluation_jobs_root,
        layout.runtime_dir / "swift-text-worker-cache",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def ensure_runtime_is_stopped(layout: RuntimeLayout) -> None:
    for pid_name in ("swift-text-worker.pid", "python-worker.pid", "control-plane.pid"):
        if (layout.runtime_dir / pid_name).exists():
            raise RuntimeError(
                f"Melix runtime metadata already exists in {layout.runtime_dir}. Run scripts/dev_down.sh first."
            )


def cleanup_runtime_artifacts(layout: RuntimeLayout) -> None:
    for artifact in (
        layout.python_socket_path,
        layout.swift_text_worker_socket_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.python_worker_metrics_path,
    ):
        artifact.unlink(missing_ok=True)


def spawn_background_process(
    *,
    cwd: Path,
    log_path: Path,
    env_overrides: dict[str, str],
    command: list[str],
) -> int:
    environment = os.environ.copy()
    environment.update(env_overrides)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("ab") as handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    return process.pid


def write_pid_file(path: Path, pid: int) -> None:
    path.write_text(f"{pid}", encoding="utf-8")


def run_wait_for_worker_ready(
    repo_root: Path,
    *,
    uv_cache_dir: Path,
    socket_path: Path,
    output_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = f"{repo_root}:{repo_root / 'services/mlx-worker-python'}"
    environment["UV_CACHE_DIR"] = os.fspath(uv_cache_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "uv",
        "run",
        "--project",
        os.fspath(repo_root / "services/mlx-worker-python"),
        "python",
        os.fspath(repo_root / "scripts" / "wait_for_worker_ready.py"),
        "--socket-path",
        os.fspath(socket_path),
    ]
    with output_path.open("wb") as handle:
        result = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Worker readiness probe failed for {socket_path}. See {output_path}.")


def wait_for_http_ready(http_port: str, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.perf_counter() + timeout_seconds
    url = f"http://127.0.0.1:{http_port}/v1/models"

    while True:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, OSError):
            pass
        if time.perf_counter() >= deadline:
            raise RuntimeError("Melix did not become ready.")
        time.sleep(0.5)


def write_runtime_environment(layout: RuntimeLayout) -> Path:
    env_path = layout.runtime_dir / "env.sh"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    exports = {
        "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
        "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
        "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
        "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
        "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
        "MELIX_HTTP_PORT": layout.http_port,
        "MELIX_BACKEND_MODE": layout.python_backend_mode,
        "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": layout.swift_text_worker_backend_mode,
        "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(layout.control_plane_metrics_path),
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": os.fspath(layout.swift_text_worker_metrics_path),
        "MELIX_PYTHON_WORKER_METRICS_PATH": os.fspath(layout.python_worker_metrics_path),
    }
    if layout.service_instance_name:
        exports["MELIX_SERVICE_INSTANCE_NAME"] = layout.service_instance_name
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.extend(f'export {key}="{value}"' for key, value in exports.items())
    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return env_path


def start_stack(options: DevUpOptions) -> None:
    repo_root = ROOT
    layout = compute_runtime_layout(repo_root)
    ensure_runtime_directories(layout)
    ensure_runtime_is_stopped(layout)
    cleanup_runtime_artifacts(layout)

    swift_text_command = build_swift_launch_command(
        repo_root,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=options.prefer_built,
    )
    swift_text_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "swift-text-worker.log",
        env_overrides={
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": layout.swift_text_worker_backend_mode,
            "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": os.fspath(layout.swift_text_worker_metrics_path),
            "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS": str(time.perf_counter_ns()),
            "MELIX_DEV_TEXT_MODEL_PATH": os.environ.get("MELIX_DEV_TEXT_MODEL_PATH", ""),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
        },
        command=swift_text_command,
    )
    write_pid_file(layout.runtime_dir / "swift-text-worker.pid", swift_text_pid)
    run_wait_for_worker_ready(
        repo_root,
        uv_cache_dir=layout.uv_cache_dir,
        socket_path=layout.swift_text_worker_socket_path,
        output_path=layout.runtime_dir / "swift-text-worker.ready.log",
    )

    python_worker_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "python-worker.log",
        env_overrides={
            "PYTHONPATH": f"{repo_root}:{repo_root / 'services/mlx-worker-python'}",
            "UV_CACHE_DIR": os.fspath(layout.uv_cache_dir),
            "MELIX_PYTHON_WORKER_METRICS_PATH": os.fspath(layout.python_worker_metrics_path),
            "MELIX_PYTHON_WORKER_STARTUP_T0_NS": str(time.perf_counter_ns()),
            "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
            "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
            "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
            "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
        },
        command=[
            "uv",
            "run",
            "--project",
            os.fspath(repo_root / "services/mlx-worker-python"),
            "python",
            "-m",
            "worker.bootstrap",
            "--socket-path",
            os.fspath(layout.python_socket_path),
            "--backend-mode",
            layout.python_backend_mode,
        ],
    )
    write_pid_file(layout.runtime_dir / "python-worker.pid", python_worker_pid)
    run_wait_for_worker_ready(
        repo_root,
        uv_cache_dir=layout.uv_cache_dir,
        socket_path=layout.python_socket_path,
        output_path=layout.runtime_dir / "python-worker.ready.log",
    )

    control_plane_command = build_swift_launch_command(
        repo_root,
        package_path="services/control-plane-swift",
        product_name="melix-control-plane",
        prefer_built=options.prefer_built,
    )
    control_plane_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "control-plane.log",
        env_overrides={
            "MELIX_HTTP_PORT": layout.http_port,
            "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
            "MELIX_REPO_ROOT": os.fspath(repo_root),
            "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(layout.control_plane_metrics_path),
            "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
            "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
        },
        command=control_plane_command,
    )
    write_pid_file(layout.runtime_dir / "control-plane.pid", control_plane_pid)

    env_path = write_runtime_environment(layout)
    try:
        wait_for_http_ready(layout.http_port)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc} See {layout.runtime_dir / 'control-plane.log'}, "
            f"{layout.runtime_dir / 'swift-text-worker.log'}, and {layout.runtime_dir / 'python-worker.log'}."
        ) from exc

    print("Melix local stack is ready.")
    print(f"HTTP: http://127.0.0.1:{layout.http_port}")
    print(f"Swift text worker socket: {layout.swift_text_worker_socket_path}")
    print(f"Python compatibility worker socket: {layout.python_socket_path}")
    print(f"Control plane metrics: {layout.control_plane_metrics_path}")
    print(f"Swift text worker metrics: {layout.swift_text_worker_metrics_path}")
    print(f"Python worker metrics: {layout.python_worker_metrics_path}")
    print(f"Runtime env file: {env_path}")
    if layout.service_instance_name:
        print(f"Service instance: {layout.service_instance_name}")
    if options.prefer_built:
        print("Swift launch mode: prefer-built")


def _normalize_service_instance_name(value: str) -> str:
    value = value.strip().lower()
    normalized = "".join(character if character.isalnum() or character == "-" else "-" for character in value)
    return normalized.strip("-")


def main(argv: list[str] | None = None) -> int:
    options = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        start_stack(options)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
