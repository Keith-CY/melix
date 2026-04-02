from __future__ import annotations

import json
import os
import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalProductLayout:
    repo_root: Path
    home_dir: Path
    app_support_dir: Path
    runtime_dir: Path
    managed_models_dir: Path
    audio_runtime_packs_dir: Path
    logs_dir: Path
    launch_agents_dir: Path
    uv_cache_dir: Path
    swift_home_dir: Path
    module_cache_dir: Path
    python_socket_path: Path
    swift_text_worker_socket_path: Path
    control_plane_metrics_path: Path
    swift_text_worker_metrics_path: Path
    python_worker_metrics_path: Path
    python_worker_stdout_path: Path
    python_worker_stderr_path: Path
    swift_text_worker_stdout_path: Path
    swift_text_worker_stderr_path: Path
    control_plane_stdout_path: Path
    control_plane_stderr_path: Path
    environment_script_path: Path
    install_manifest_path: Path
    http_port: int


@dataclass(frozen=True)
class LaunchAgentSpec:
    label: str
    plist_path: Path
    program_arguments: list[str]
    environment: dict[str, str]
    working_directory: Path
    stdout_path: Path
    stderr_path: Path
    keep_alive: bool = True
    run_at_load: bool = True


def build_local_product_layout(
    repo_root: str | Path,
    home_dir: str | Path | None = None,
    *,
    launch_agents_dir: str | Path | None = None,
    http_port: int = 11434,
) -> LocalProductLayout:
    resolved_repo_root = Path(repo_root).expanduser().resolve()
    resolved_home_dir = Path(home_dir or Path.home()).expanduser().resolve()
    resolved_launch_agents_dir = (
        Path(launch_agents_dir).expanduser().resolve()
        if launch_agents_dir is not None
        else resolved_home_dir / "Library/LaunchAgents"
    )

    app_support_dir = resolved_home_dir / "Library/Application Support/Melix"
    runtime_dir = app_support_dir / "runtime"
    managed_models_dir = app_support_dir / "models/default-managed"
    audio_runtime_packs_dir = app_support_dir / "runtime-packs/audio"
    logs_dir = resolved_home_dir / "Library/Logs/Melix"

    return LocalProductLayout(
        repo_root=resolved_repo_root,
        home_dir=resolved_home_dir,
        app_support_dir=app_support_dir,
        runtime_dir=runtime_dir,
        managed_models_dir=managed_models_dir,
        audio_runtime_packs_dir=audio_runtime_packs_dir,
        logs_dir=logs_dir,
        launch_agents_dir=resolved_launch_agents_dir,
        uv_cache_dir=resolved_repo_root / ".uv-cache",
        swift_home_dir=resolved_repo_root / ".swift-home",
        module_cache_dir=resolved_repo_root / ".build/ModuleCache.noindex",
        python_socket_path=runtime_dir / "python-worker.sock",
        swift_text_worker_socket_path=runtime_dir / "swift-text-worker.sock",
        control_plane_metrics_path=runtime_dir / "control-plane-metrics.json",
        swift_text_worker_metrics_path=runtime_dir / "swift-text-worker-metrics.json",
        python_worker_metrics_path=runtime_dir / "python-worker-metrics.json",
        python_worker_stdout_path=logs_dir / "python-worker.stdout.log",
        python_worker_stderr_path=logs_dir / "python-worker.stderr.log",
        swift_text_worker_stdout_path=logs_dir / "swift-text-worker.stdout.log",
        swift_text_worker_stderr_path=logs_dir / "swift-text-worker.stderr.log",
        control_plane_stdout_path=logs_dir / "control-plane.stdout.log",
        control_plane_stderr_path=logs_dir / "control-plane.stderr.log",
        environment_script_path=app_support_dir / "melix-product-env.sh",
        install_manifest_path=app_support_dir / "install-manifest.json",
        http_port=http_port,
    )


def build_launch_agent_specs(
    layout: LocalProductLayout,
    *,
    swift_backend_mode: str = "deterministic",
    python_backend_mode: str = "deterministic",
    dev_text_model_path: str = "",
) -> list[LaunchAgentSpec]:
    common_swift_environment = {
        "HOME": str(layout.swift_home_dir),
        "CLANG_MODULE_CACHE_PATH": str(layout.module_cache_dir),
    }

    swift_text_environment = {
        **common_swift_environment,
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(layout.swift_text_worker_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": swift_backend_mode,
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": str(layout.swift_text_worker_metrics_path),
        "MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT": str(layout.runtime_dir / "swift-text-worker-cache"),
    }
    if dev_text_model_path:
        swift_text_environment["MELIX_DEV_TEXT_MODEL_PATH"] = dev_text_model_path

    python_environment = {
        "PYTHONPATH": f"{layout.repo_root}:{layout.repo_root / 'services/mlx-worker-python'}",
        "UV_CACHE_DIR": str(layout.uv_cache_dir),
        "MELIX_PYTHON_WORKER_METRICS_PATH": str(layout.python_worker_metrics_path),
        "MELIX_MANAGED_MODEL_ROOT": str(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": str(layout.audio_runtime_packs_dir),
    }

    control_plane_environment = {
        **common_swift_environment,
        "MELIX_HTTP_PORT": str(layout.http_port),
        "MELIX_WORKER_SOCKET_PATH": str(layout.python_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(layout.swift_text_worker_socket_path),
        "MELIX_REPO_ROOT": str(layout.repo_root),
        "MELIX_CONTROL_PLANE_METRICS_PATH": str(layout.control_plane_metrics_path),
        "MELIX_MANAGED_MODEL_ROOT": str(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": str(layout.audio_runtime_packs_dir),
    }

    return [
        LaunchAgentSpec(
            label="io.melix.swift-text-worker",
            plist_path=layout.launch_agents_dir / "io.melix.swift-text-worker.plist",
            program_arguments=[
                "/usr/bin/env",
                "swift",
                "run",
                "--package-path",
                str(layout.repo_root / "services/mlx-text-worker-swift"),
                "melix-text-worker-swift",
            ],
            environment=swift_text_environment,
            working_directory=layout.repo_root,
            stdout_path=layout.swift_text_worker_stdout_path,
            stderr_path=layout.swift_text_worker_stderr_path,
        ),
        LaunchAgentSpec(
            label="io.melix.python-worker",
            plist_path=layout.launch_agents_dir / "io.melix.python-worker.plist",
            program_arguments=[
                "/usr/bin/env",
                "uv",
                "run",
                "--project",
                str(layout.repo_root / "services/mlx-worker-python"),
                "python",
                "-m",
                "worker.bootstrap",
                "--socket-path",
                str(layout.python_socket_path),
                "--backend-mode",
                python_backend_mode,
            ],
            environment=python_environment,
            working_directory=layout.repo_root,
            stdout_path=layout.python_worker_stdout_path,
            stderr_path=layout.python_worker_stderr_path,
        ),
        LaunchAgentSpec(
            label="io.melix.control-plane",
            plist_path=layout.launch_agents_dir / "io.melix.control-plane.plist",
            program_arguments=[
                "/usr/bin/env",
                "swift",
                "run",
                "--package-path",
                str(layout.repo_root / "services/control-plane-swift"),
                "melix-control-plane",
            ],
            environment=control_plane_environment,
            working_directory=layout.repo_root,
            stdout_path=layout.control_plane_stdout_path,
            stderr_path=layout.control_plane_stderr_path,
        ),
    ]


def render_launch_agent_plist(spec: LaunchAgentSpec) -> str:
    payload: dict[str, Any] = {
        "Label": spec.label,
        "ProgramArguments": spec.program_arguments,
        "WorkingDirectory": str(spec.working_directory),
        "StandardOutPath": str(spec.stdout_path),
        "StandardErrorPath": str(spec.stderr_path),
        "RunAtLoad": spec.run_at_load,
        "KeepAlive": spec.keep_alive,
    }
    if spec.environment:
        payload["EnvironmentVariables"] = spec.environment

    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False).decode("utf-8")


def write_local_product_artifacts(
    layout: LocalProductLayout,
    *,
    swift_backend_mode: str = "deterministic",
    python_backend_mode: str = "deterministic",
    dev_text_model_path: str = "",
) -> dict[str, Any]:
    specs = build_launch_agent_specs(
        layout,
        swift_backend_mode=swift_backend_mode,
        python_backend_mode=python_backend_mode,
        dev_text_model_path=dev_text_model_path,
    )

    directories = [
        layout.app_support_dir,
        layout.runtime_dir,
        layout.managed_models_dir,
        layout.audio_runtime_packs_dir,
        layout.logs_dir,
        layout.launch_agents_dir,
        layout.uv_cache_dir,
        layout.swift_home_dir,
        layout.module_cache_dir,
        layout.runtime_dir / "swift-text-worker-cache",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    plist_paths: dict[str, str] = {}
    for spec in specs:
        spec.plist_path.write_text(render_launch_agent_plist(spec))
        plist_paths[spec.label] = str(spec.plist_path)

    layout.environment_script_path.write_text(render_environment_script(layout))
    manifest = {
        "repo_root": str(layout.repo_root),
        "app_support_dir": str(layout.app_support_dir),
        "runtime_dir": str(layout.runtime_dir),
        "managed_models_dir": str(layout.managed_models_dir),
        "audio_runtime_packs_dir": str(layout.audio_runtime_packs_dir),
        "logs_dir": str(layout.logs_dir),
        "launch_agents_dir": str(layout.launch_agents_dir),
        "environment_script_path": str(layout.environment_script_path),
        "install_manifest_path": str(layout.install_manifest_path),
        "http_port": layout.http_port,
        "ready_probe_url": f"http://127.0.0.1:{layout.http_port}/v1/models",
        "plists": plist_paths,
        "bootstrap_commands": [
            f'launchctl bootstrap gui/{os.getuid()} "{spec.plist_path}"'
            for spec in specs
        ],
        "bootout_commands": [
            f'launchctl bootout gui/{os.getuid()} "{spec.plist_path}"'
            for spec in specs
        ],
    }
    layout.install_manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def render_environment_script(layout: LocalProductLayout) -> str:
    exports = {
        "MELIX_APP_SUPPORT_DIR": str(layout.app_support_dir),
        "MELIX_RUNTIME_DIR": str(layout.runtime_dir),
        "MELIX_MANAGED_MODEL_ROOT": str(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": str(layout.audio_runtime_packs_dir),
        "MELIX_WORKER_SOCKET_PATH": str(layout.python_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(layout.swift_text_worker_socket_path),
        "MELIX_HTTP_PORT": str(layout.http_port),
        "MELIX_CONTROL_PLANE_METRICS_PATH": str(layout.control_plane_metrics_path),
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": str(layout.swift_text_worker_metrics_path),
        "MELIX_PYTHON_WORKER_METRICS_PATH": str(layout.python_worker_metrics_path),
    }
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.extend(f'export {key}="{value}"' for key, value in exports.items())
    lines.append("")
    return "\n".join(lines)
