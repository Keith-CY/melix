from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import IO

from worker.productization.install_assets import (
    LaunchAgentSpec,
    LocalProductLayout,
    build_launch_agent_specs,
    build_local_product_layout,
)
from worker.productization.packaging_targets import build_packaging_target_metadata


DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME = "homebrew"


@dataclass
class ManagedServiceProcess:
    spec: LaunchAgentSpec
    process: subprocess.Popen[bytes]
    stdout_handle: IO[bytes]
    stderr_handle: IO[bytes]


def ensure_runtime_directories(layout: LocalProductLayout) -> None:
    directories = [
        layout.melix_home_dir,
        layout.melix_home_dir / "config",
        layout.melix_home_dir / "state",
        layout.melix_home_dir / "secrets",
        layout.install_dir,
        layout.runtime_dir,
        layout.managed_models_dir,
        layout.audio_runtime_packs_dir,
        layout.model_ops_jobs_root,
        layout.evaluation_jobs_root,
        layout.logs_dir,
        layout.runtime_dir / "swift-text-worker-cache",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def build_homebrew_service_specs(
    *,
    repo_root: str | Path,
    bin_dir: str | Path,
    home_dir: str | Path | None = None,
    http_port: int = 12436,
    service_instance_name: str = DEFAULT_HOMEBREW_SERVICE_INSTANCE_NAME,
    swift_backend_mode: str = "swift",
    python_backend_mode: str = "auto",
    dev_text_model_path: str = "",
) -> tuple[LocalProductLayout, list[LaunchAgentSpec]]:
    resolved_repo_root = Path(repo_root).expanduser().resolve()
    resolved_bin_dir = Path(bin_dir).expanduser().resolve()
    layout = build_local_product_layout(
        repo_root=resolved_repo_root,
        home_dir=home_dir,
        http_port=http_port,
        service_instance_name=service_instance_name,
    )
    launch_specs = build_launch_agent_specs(
        layout,
        swift_backend_mode=swift_backend_mode,
        python_backend_mode=python_backend_mode,
        dev_text_model_path=dev_text_model_path,
    )
    service_specs: list[LaunchAgentSpec] = []
    for spec in launch_specs:
        if spec.label.endswith(".swift-text-worker"):
            program_arguments = [str(resolved_bin_dir / "melix-text-worker-swift")]
        elif spec.label.endswith(".control-plane"):
            program_arguments = [str(resolved_bin_dir / "melix-control-plane")]
        else:
            program_arguments = [
                "/usr/bin/env",
                "uv",
                "run",
                "--project",
                str(resolved_repo_root / "services/mlx-worker-python"),
                "python",
                "-m",
                "worker.bootstrap",
                "--socket-path",
                str(layout.python_socket_path),
                "--backend-mode",
                python_backend_mode,
            ]
        service_specs.append(replace(spec, program_arguments=program_arguments))
    return layout, service_specs


def build_homebrew_service_manifest(
    layout: LocalProductLayout,
    specs: list[LaunchAgentSpec],
) -> dict[str, object]:
    target_metadata = build_packaging_target_metadata(
        "homebrew_service",
        product_version=layout.product_version,
        update_channel_path=layout.update_channel_path,
        service_instance_name=layout.service_instance_name,
    )
    return {
        **target_metadata,
        "repo_root": str(layout.repo_root),
        "bin_dir": str(Path(specs[0].program_arguments[0]).resolve().parent) if specs else "",
        "melix_home_dir": str(layout.melix_home_dir),
        "install_dir": str(layout.install_dir),
        "runtime_dir": str(layout.runtime_dir),
        "logs_dir": str(layout.logs_dir),
        "requested_http_port": layout.requested_http_port,
        "http_port": layout.http_port,
        "http_port_auto_selected": layout.requested_http_port != layout.http_port,
        "ready_probe_url": f"http://127.0.0.1:{layout.http_port}/v1/models",
        "services": [
            {
                "label": spec.label,
                "program_arguments": spec.program_arguments,
                "working_directory": str(spec.working_directory),
                "stdout_path": str(spec.stdout_path),
                "stderr_path": str(spec.stderr_path),
            }
            for spec in specs
        ],
    }


class ManagedServiceProcessGroup:
    def __init__(self, specs: list[LaunchAgentSpec]) -> None:
        self.specs = specs
        self._entries: list[ManagedServiceProcess] = []

    def start(self) -> None:
        if self._entries:
            raise RuntimeError("process group already started")
        for spec in self.specs:
            spec.stdout_path.parent.mkdir(parents=True, exist_ok=True)
            spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_handle = spec.stdout_path.open("ab")
            stderr_handle = spec.stderr_path.open("ab")
            environment = os.environ.copy()
            environment.update(spec.environment)
            process = subprocess.Popen(
                spec.program_arguments,
                cwd=spec.working_directory,
                env=environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            self._entries.append(
                ManagedServiceProcess(
                    spec=spec,
                    process=process,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                )
            )

    def poll_failures(self) -> list[tuple[str, int]]:
        failures: list[tuple[str, int]] = []
        for entry in self._entries:
            code = entry.process.poll()
            if code is not None and code != 0:
                failures.append((entry.spec.label, code))
        return failures

    def shutdown(self, *, grace_seconds: float = 5.0) -> list[tuple[str, int | None]]:
        results: list[tuple[str, int | None]] = []
        running_entries = [entry for entry in self._entries if entry.process.poll() is None]
        for entry in running_entries:
            entry.process.terminate()
        deadline = time.monotonic() + grace_seconds
        for entry in running_entries:
            remaining = deadline - time.monotonic()
            try:
                entry.process.wait(timeout=max(0.1, remaining))
            except subprocess.TimeoutExpired:
                entry.process.kill()
                entry.process.wait(timeout=1.0)
        for entry in self._entries:
            results.append((entry.spec.label, entry.process.poll()))
            entry.stdout_handle.close()
            entry.stderr_handle.close()
        self._entries = []
        return results


def run_homebrew_service_bundle(
    specs: list[LaunchAgentSpec],
    *,
    grace_seconds: float = 5.0,
    poll_interval_seconds: float = 0.25,
) -> int:
    group = ManagedServiceProcessGroup(specs)
    group.start()
    requested_stop = False

    def _handle_signal(_signum: int, _frame: object) -> None:
        nonlocal requested_stop
        requested_stop = True

    previous_sigint = signal.signal(signal.SIGINT, _handle_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
    try:
        while True:
            failures = group.poll_failures()
            if failures:
                group.shutdown(grace_seconds=grace_seconds)
                return failures[0][1]
            if requested_stop:
                group.shutdown(grace_seconds=grace_seconds)
                return 0
            time.sleep(poll_interval_seconds)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
