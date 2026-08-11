#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USAGE_TEXT = """Usage: bash scripts/dev_app_up.sh

Incrementally builds the current Swift products, starts the Melix backend stack,
and launches the current melix-menubar app from direct executables."""


def _load_dev_up_module():
    module_path = ROOT / "scripts" / "dev_up.py"
    spec = importlib.util.spec_from_file_location("melix_dev_up_shared", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dev_up = _load_dev_up_module()


def print_usage(*, stream) -> None:
    print(USAGE_TEXT, file=stream)


def parse_args(argv: list[str]) -> None:
    for argument in argv:
        if argument in {"-h", "--help"}:
            print_usage(stream=sys.stdout)
            raise SystemExit(0)
        print(f"Unknown argument: {argument}", file=sys.stderr)
        print_usage(stream=sys.stderr)
        raise SystemExit(2)


def start_full_app() -> None:
    repo_root = ROOT
    layout = dev_up.compute_runtime_layout(repo_root)
    menubar_pid_path = layout.runtime_dir / "menubar.pid"

    if menubar_pid_path.exists():
        raise RuntimeError(
            f"Melix runtime metadata already exists in {layout.runtime_dir}. Run scripts/dev_down.sh first."
        )

    initial_mcp_credential_environment_keys = dev_up.active_mcp_credential_environment_keys(
        environment=os.environ,
        melix_home_dir=layout.melix_home_dir,
    )

    menubar_command = dev_up.build_swift_launch_command(
        repo_root,
        package_path="apps/macos-menubar",
        product_name="melix-menubar",
        prefer_built=False,
    )
    dev_up.start_stack(dev_up.DevUpOptions(prefer_built=False))
    try:
        # Recompute after backend startup so the menubar inherits the same runtime contract.
        layout = dev_up.compute_runtime_layout(repo_root)
        current_mcp_credential_environment_keys = (
            dev_up.active_mcp_credential_environment_keys(
                environment=os.environ,
                melix_home_dir=layout.melix_home_dir,
            )
        )
        private_app_environment_keys = (
            *dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS,
            *dev_up.validate_frozen_mcp_credential_environment_key_snapshot(
                initial_mcp_credential_environment_keys,
                current_mcp_credential_environment_keys,
            ),
        )
        menubar_log_path = layout.runtime_dir / "menubar.log"
        menubar_pid = dev_up.spawn_background_process(
            cwd=repo_root,
            log_path=menubar_log_path,
            base_environment=dev_up.sanitized_process_environment(
                base_environment=dev_up.app_parent_environment(),
                unset_environment_keys=private_app_environment_keys,
            ),
            unset_environment_keys=private_app_environment_keys,
            env_overrides={
                "MELIX_REPO_ROOT": os.fspath(repo_root),
                "MELIX_HOME": os.fspath(layout.melix_home_dir),
                "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
                "MELIX_CONTROL_PLANE_SOCKET_PATH": os.fspath(
                    layout.control_plane_socket_path
                ),
                "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
                "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
                "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
                "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
                "MELIX_GATEWAY_CONFIG_STORE_PATH": os.fspath(layout.gateway_config_store_path),
                "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH": os.fspath(layout.gateway_serving_defaults_store_path),
                "MELIX_IMAGE_DEFAULTS_STORE_PATH": os.fspath(layout.image_defaults_store_path),
                "MELIX_HTTP_PORT": layout.http_port,
                "MELIX_MENU_BAR_STARTUP_SURFACE": "console",
                "MELIX_MENU_BAR_PRESENTATION_MODE": "dock-and-tray",
                "MELIX_MENU_BAR_TERMINATION_MODE": "dev-down-script",
            },
            command=menubar_command,
            pass_fds=(),
        )
        dev_up.write_pid_file(menubar_pid_path, menubar_pid)
    except Exception as startup_error:
        try:
            dev_up.rollback_started_stack(layout)
        except RuntimeError as rollback_error:
            raise RuntimeError(f"{startup_error} {rollback_error}") from startup_error
        raise

    print("Melix full app is ready.")
    print(f"Menu bar log: {menubar_log_path}")
    print(f"Menu bar pid file: {menubar_pid_path}")


def main(argv: list[str] | None = None) -> int:
    try:
        parse_args(list(sys.argv[1:] if argv is None else argv))
        start_full_app()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
