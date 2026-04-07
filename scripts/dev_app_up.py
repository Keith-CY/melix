#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USAGE_TEXT = """Usage: bash scripts/dev_app_up.sh

Starts the built Melix backend stack and launches the built melix-menubar app.
Fails fast when required Swift build artifacts are missing."""


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


def resolve_built_menubar_binary(repo_root: Path) -> Path:
    try:
        return dev_up.resolve_built_swift_product_binary(
            repo_root,
            package_path="apps/macos-menubar",
            product_name="melix-menubar",
        )
    except RuntimeError as exc:
        package_root = repo_root / "apps" / "macos-menubar"
        raise RuntimeError(
            f"Built Swift product is missing for 'melix-menubar' under {package_root / '.build'}.\n"
            f"Run `make swift-test`, `swift test --package-path {package_root}`, or "
            f"`swift build --package-path {package_root}` before using scripts/dev_app_up.sh."
        ) from exc


def start_full_app() -> None:
    repo_root = ROOT
    menubar_binary = resolve_built_menubar_binary(repo_root)
    layout = dev_up.compute_runtime_layout(repo_root)
    menubar_pid_path = layout.runtime_dir / "menubar.pid"

    if menubar_pid_path.exists():
        raise RuntimeError(
            f"Melix runtime metadata already exists in {layout.runtime_dir}. Run scripts/dev_down.sh first."
        )

    dev_up.start_stack(dev_up.DevUpOptions(prefer_built=True))

    # Recompute after backend startup so the menubar inherits the same runtime contract.
    layout = dev_up.compute_runtime_layout(repo_root)
    menubar_log_path = layout.runtime_dir / "menubar.log"
    menubar_pid = dev_up.spawn_background_process(
        cwd=repo_root,
        log_path=menubar_log_path,
        env_overrides={
            "MELIX_REPO_ROOT": os.fspath(repo_root),
            "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
            "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
            "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
            "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
            "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
            "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
            "MELIX_HTTP_PORT": layout.http_port,
            "MELIX_MENU_BAR_STARTUP_SURFACE": "console",
            "MELIX_MENU_BAR_PRESENTATION_MODE": "dock-and-tray",
            "MELIX_MENU_BAR_TERMINATION_MODE": "dev-down-script",
        },
        command=[os.fspath(menubar_binary)],
    )
    dev_up.write_pid_file(menubar_pid_path, menubar_pid)

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
