from __future__ import annotations

import json
import os
import plistlib
import shutil
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from worker.productization.startup_signals import (
    default_update_channel_path,
    read_product_version,
    resolve_http_port,
)
from worker.productization.packaging_targets import build_packaging_target_metadata


@dataclass(frozen=True)
class LocalProductLayout:
    service_instance_name: str
    repo_root: Path
    home_dir: Path
    app_support_dir: Path
    runtime_dir: Path
    managed_models_dir: Path
    audio_runtime_packs_dir: Path
    model_ops_jobs_root: Path
    evaluation_jobs_root: Path
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
    update_channel_path: Path
    product_version: str
    requested_http_port: int
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
    service_instance_name: str = "",
    prefer_available_http_port: bool = False,
    product_version: str = "",
    update_channel_path: str | Path | None = None,
) -> LocalProductLayout:
    resolved_repo_root = Path(repo_root).expanduser().resolve()
    resolved_home_dir = Path(home_dir or Path.home()).expanduser().resolve()
    resolved_launch_agents_dir = (
        Path(launch_agents_dir).expanduser().resolve()
        if launch_agents_dir is not None
        else resolved_home_dir / "Library/LaunchAgents"
    )

    normalized_instance_name = _normalize_service_instance_name(service_instance_name)
    resolved_http_port = resolve_http_port(
        http_port,
        prefer_available_http_port=prefer_available_http_port,
    )
    resolved_product_version = product_version or _resolve_product_version(resolved_repo_root)
    resolved_update_channel_path = (
        Path(update_channel_path).expanduser().resolve()
        if update_channel_path is not None
        else default_update_channel_path(resolved_repo_root)
    )
    if normalized_instance_name:
        app_support_dir = (
            resolved_home_dir
            / "Library/Application Support/Melix/sidecars"
            / normalized_instance_name
        )
        logs_dir = resolved_home_dir / "Library/Logs/Melix/sidecars" / normalized_instance_name
        environment_script_path = app_support_dir / f"melix-sidecar-{normalized_instance_name}-env.sh"
    else:
        app_support_dir = resolved_home_dir / "Library/Application Support/Melix"
        logs_dir = resolved_home_dir / "Library/Logs/Melix"
        environment_script_path = app_support_dir / "melix-product-env.sh"
    runtime_dir = app_support_dir / "runtime"
    managed_models_dir = app_support_dir / "models/default-managed"
    audio_runtime_packs_dir = app_support_dir / "runtime-packs/audio"
    model_ops_jobs_root = app_support_dir / "jobs/model-ops"
    evaluation_jobs_root = model_ops_jobs_root / "evaluation"

    return LocalProductLayout(
        service_instance_name=normalized_instance_name,
        repo_root=resolved_repo_root,
        home_dir=resolved_home_dir,
        app_support_dir=app_support_dir,
        runtime_dir=runtime_dir,
        managed_models_dir=managed_models_dir,
        audio_runtime_packs_dir=audio_runtime_packs_dir,
        model_ops_jobs_root=model_ops_jobs_root,
        evaluation_jobs_root=evaluation_jobs_root,
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
        environment_script_path=environment_script_path,
        install_manifest_path=app_support_dir / "install-manifest.json",
        update_channel_path=resolved_update_channel_path,
        product_version=resolved_product_version,
        requested_http_port=http_port,
        http_port=resolved_http_port,
    )


def build_launch_agent_specs(
    layout: LocalProductLayout,
    *,
    swift_backend_mode: str = "swift",
    python_backend_mode: str = "auto",
    dev_text_model_path: str = "",
) -> list[LaunchAgentSpec]:
    python_launcher = shutil.which("uv")
    python_program_arguments = (
        [
            python_launcher,
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
        ]
        if python_launcher
        else [
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
        ]
    )

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
        "MELIX_MODEL_OPS_JOBS_ROOT": str(layout.model_ops_jobs_root),
        "MELIX_EVALUATION_JOBS_ROOT": str(layout.evaluation_jobs_root),
    }
    if layout.service_instance_name:
        python_environment["MELIX_SERVICE_INSTANCE_NAME"] = layout.service_instance_name

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
    if layout.service_instance_name:
        control_plane_environment["MELIX_SERVICE_INSTANCE_NAME"] = layout.service_instance_name

    label_prefix = "io.melix"
    if layout.service_instance_name:
        label_prefix = f"{label_prefix}.{layout.service_instance_name}"

    return [
        LaunchAgentSpec(
            label=f"{label_prefix}.swift-text-worker",
            plist_path=layout.launch_agents_dir / f"{label_prefix}.swift-text-worker.plist",
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
            label=f"{label_prefix}.python-worker",
            plist_path=layout.launch_agents_dir / f"{label_prefix}.python-worker.plist",
            program_arguments=python_program_arguments,
            environment=python_environment,
            working_directory=layout.repo_root,
            stdout_path=layout.python_worker_stdout_path,
            stderr_path=layout.python_worker_stderr_path,
        ),
        LaunchAgentSpec(
            label=f"{label_prefix}.control-plane",
            plist_path=layout.launch_agents_dir / f"{label_prefix}.control-plane.plist",
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
    swift_backend_mode: str = "swift",
    python_backend_mode: str = "auto",
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
        layout.model_ops_jobs_root,
        layout.evaluation_jobs_root,
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
    target_metadata = build_packaging_target_metadata(
        "launch_agents_checkout",
        product_version=layout.product_version,
        update_channel_path=layout.update_channel_path,
        service_instance_name=layout.service_instance_name,
    )
    manifest = {
        **target_metadata,
        "repo_root": str(layout.repo_root),
        "app_support_dir": str(layout.app_support_dir),
        "runtime_dir": str(layout.runtime_dir),
        "managed_models_dir": str(layout.managed_models_dir),
        "audio_runtime_packs_dir": str(layout.audio_runtime_packs_dir),
        "model_ops_jobs_root": str(layout.model_ops_jobs_root),
        "evaluation_jobs_root": str(layout.evaluation_jobs_root),
        "logs_dir": str(layout.logs_dir),
        "launch_agents_dir": str(layout.launch_agents_dir),
        "environment_script_path": str(layout.environment_script_path),
        "install_manifest_path": str(layout.install_manifest_path),
        "requested_http_port": layout.requested_http_port,
        "http_port": layout.http_port,
        "http_port_auto_selected": layout.requested_http_port != layout.http_port,
        "ready_probe_url": f"http://127.0.0.1:{layout.http_port}/v1/models",
        "control_plane_stdout_path": str(layout.control_plane_stdout_path),
        "control_plane_stderr_path": str(layout.control_plane_stderr_path),
        "swift_text_worker_stdout_path": str(layout.swift_text_worker_stdout_path),
        "swift_text_worker_stderr_path": str(layout.swift_text_worker_stderr_path),
        "python_worker_stdout_path": str(layout.python_worker_stdout_path),
        "python_worker_stderr_path": str(layout.python_worker_stderr_path),
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
    target_metadata = build_packaging_target_metadata(
        "launch_agents_checkout",
        product_version=layout.product_version,
        update_channel_path=layout.update_channel_path,
        service_instance_name=layout.service_instance_name,
    )
    exports = {
        "MELIX_LOGICAL_PRODUCT_ID": str(target_metadata["logical_product_identity"]),
        "MELIX_PACKAGING_TARGET_ID": str(target_metadata["packaging_target_id"]),
        "MELIX_PACKAGING_KIND": str(target_metadata["packaging_kind"]),
        "MELIX_PRODUCT_VERSION": str(layout.product_version),
        "MELIX_UPDATE_CHANNEL_PATH": str(layout.update_channel_path),
        "MELIX_APP_SUPPORT_DIR": str(layout.app_support_dir),
        "MELIX_RUNTIME_DIR": str(layout.runtime_dir),
        "MELIX_MANAGED_MODEL_ROOT": str(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": str(layout.audio_runtime_packs_dir),
        "MELIX_MODEL_OPS_JOBS_ROOT": str(layout.model_ops_jobs_root),
        "MELIX_EVALUATION_JOBS_ROOT": str(layout.evaluation_jobs_root),
        "MELIX_WORKER_SOCKET_PATH": str(layout.python_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": str(layout.swift_text_worker_socket_path),
        "MELIX_HTTP_PORT": str(layout.http_port),
        "MELIX_CONTROL_PLANE_METRICS_PATH": str(layout.control_plane_metrics_path),
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": str(layout.swift_text_worker_metrics_path),
        "MELIX_PYTHON_WORKER_METRICS_PATH": str(layout.python_worker_metrics_path),
    }
    if layout.service_instance_name:
        exports["MELIX_SERVICE_INSTANCE_NAME"] = layout.service_instance_name
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.extend(f'export {key}="{value}"' for key, value in exports.items())
    lines.append("")
    return "\n".join(lines)


def _normalize_service_instance_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return normalized


def _resolve_product_version(repo_root: Path) -> str:
    try:
        return read_product_version(repo_root)
    except (FileNotFoundError, ValueError):
        return "0.1.0"
