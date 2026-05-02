from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.productization.packaging_targets import build_packaging_target_metadata
from worker.productization.startup_signals import default_update_channel_path


_BUNDLED_EVALUATION_FIXTURE_IDS = ("top200.event-extraction.top20.v1",)


@dataclass(frozen=True)
class MacOSAppBundleLayout:
    app_path: Path
    contents_path: Path
    macos_path: Path
    resources_path: Path
    plist_path: Path
    launcher_path: Path
    bundled_app_binary_path: Path
    bundled_cli_binary_path: Path
    bundled_swift_worker_binary_path: Path
    bundled_python_runtime_path: Path
    bundled_python_executable_path: Path
    bundled_site_packages_path: Path
    bundled_repo_root_path: Path
    bundled_icon_path: Path
    bundled_wait_script_path: Path
    embedded_env_script_path: Path
    packaging_target_manifest_path: Path


def build_macos_app_bundle_layout(output_path: str | Path, app_name: str = "Melix") -> MacOSAppBundleLayout:
    app_path = Path(output_path).expanduser().resolve()
    contents_path = app_path / "Contents"
    macos_path = contents_path / "MacOS"
    resources_path = contents_path / "Resources"
    python_runtime_path = resources_path / "python-runtime"
    return MacOSAppBundleLayout(
        app_path=app_path,
        contents_path=contents_path,
        macos_path=macos_path,
        resources_path=resources_path,
        plist_path=contents_path / "Info.plist",
        launcher_path=macos_path / app_name,
        bundled_app_binary_path=resources_path / "melix-menubar",
        bundled_cli_binary_path=resources_path / "melix",
        bundled_swift_worker_binary_path=resources_path / "melix-text-worker-swift",
        bundled_python_runtime_path=python_runtime_path,
        bundled_python_executable_path=python_runtime_path / "bin/python3",
        bundled_site_packages_path=resources_path / "python-site-packages",
        bundled_repo_root_path=resources_path / "repo",
        bundled_icon_path=resources_path / "MelixAppIcon.icns",
        bundled_wait_script_path=resources_path / "repo/scripts/wait_for_worker_ready.py",
        embedded_env_script_path=resources_path / "melix-product-env.sh",
        packaging_target_manifest_path=resources_path / "packaging-target-manifest.json",
    )


def resolve_python_runtime_root(python_executable: str | Path) -> Path:
    executable = Path(python_executable).expanduser().resolve()
    return executable.parent.parent


def resolve_site_packages_root(repo_root: str | Path) -> Path:
    repo_root_path = Path(repo_root).expanduser().resolve()
    lib_root = repo_root_path / ".venv/lib"
    best_entry_name: str | None = None
    best_entry: Path | None = None

    for entry in os.scandir(lib_root):
        if not entry.name.startswith("python"):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue

        site_packages = Path(entry.path) / "site-packages"
        if not site_packages.is_dir():
            continue

        if best_entry_name is None or entry.name < best_entry_name:
            best_entry_name = entry.name
            best_entry = site_packages

    if best_entry is None:
        raise FileNotFoundError(f"Unable to locate site-packages under {lib_root}")
    return best_entry


def render_info_plist(*, app_name: str, bundle_id: str, version: str, icon_file: str) -> bytes:
    payload: dict[str, Any] = {
        "CFBundleDisplayName": app_name,
        "CFBundleExecutable": app_name,
        "CFBundleIconFile": icon_file,
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHighResolutionCapable": True,
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)


def render_portable_environment_script(
    *,
    product_version: str,
    update_channel_path: str | Path,
    logical_product_identity: str,
    packaging_target_id: str,
    packaging_kind: str,
    app_support_name: str = "Melix",
) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            f'export MELIX_LOGICAL_PRODUCT_ID="{logical_product_identity}"',
            f'export MELIX_PACKAGING_TARGET_ID="{packaging_target_id}"',
            f'export MELIX_PACKAGING_KIND="{packaging_kind}"',
            f'export MELIX_PRODUCT_VERSION="{product_version}"',
            f'export MELIX_UPDATE_CHANNEL_PATH="{Path(update_channel_path).expanduser().resolve()}"',
            f'export MELIX_APP_SUPPORT_DIR="$HOME/Library/Application Support/{app_support_name}"',
            'export MELIX_HOME="$MELIX_APP_SUPPORT_DIR"',
            'export MELIX_RUNTIME_DIR="$MELIX_APP_SUPPORT_DIR/runtime"',
            'export MELIX_MANAGED_MODEL_ROOT="$MELIX_APP_SUPPORT_DIR/models/default-managed"',
            'export MELIX_AUDIO_RUNTIME_PACK_ROOT="$MELIX_APP_SUPPORT_DIR/runtime-packs/audio"',
            'export MELIX_MODEL_OPS_JOBS_ROOT="$MELIX_APP_SUPPORT_DIR/jobs/model-ops"',
            'export MELIX_EVALUATION_JOBS_ROOT="$MELIX_APP_SUPPORT_DIR/jobs/evaluation"',
            'export MELIX_BACKEND_MODE="auto"',
            'export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="swift"',
            'export MELIX_LOGS_DIR="$HOME/Library/Logs/Melix"',
            "",
        ]
    )


def render_launcher_script(
    *,
    app_name: str,
    bundle_repo_root: str | Path,
    bundled_app_binary_name: str,
    bundled_cli_binary_name: str,
    bundled_swift_worker_binary_name: str,
    bundled_python_executable_relative_path: str,
    bundled_site_packages_relative_path: str,
    wait_script_relative_path: str,
    menu_bar_presentation_mode: str = "dock-and-tray",
    app_support_name: str = "Melix",
) -> str:
    repo_root = Path(bundle_repo_root)
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'CONTENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'RESOURCES_DIR="$CONTENTS_DIR/Resources"',
            f'export MELIX_REPO_ROOT="$RESOURCES_DIR/{repo_root.as_posix()}"',
            'source "$RESOURCES_DIR/melix-product-env.sh"',
            f'export MELIX_CLI="$RESOURCES_DIR/{bundled_cli_binary_name}"',
            'mkdir -p "$MELIX_RUNTIME_DIR" "$MELIX_LOGS_DIR" "$MELIX_RUNTIME_DIR/swift-text-worker-cache" "$MELIX_MANAGED_MODEL_ROOT" "$MELIX_AUDIO_RUNTIME_PACK_ROOT" "$MELIX_MODEL_OPS_JOBS_ROOT" "$MELIX_EVALUATION_JOBS_ROOT"',
            'RUN_TOKEN="${MELIX_RUN_TOKEN:-$$}"',
            'export MELIX_WORKER_SOCKET_PATH="$MELIX_RUNTIME_DIR/python-worker-${RUN_TOKEN}.sock"',
            'export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="$MELIX_RUNTIME_DIR/swift-text-worker-${RUN_TOKEN}.sock"',
            'export MELIX_CONTROL_PLANE_METRICS_PATH="$MELIX_RUNTIME_DIR/control-plane-metrics-${RUN_TOKEN}.json"',
            'export MELIX_SWIFT_TEXT_WORKER_METRICS_PATH="$MELIX_RUNTIME_DIR/swift-text-worker-metrics-${RUN_TOKEN}.json"',
            'export MELIX_PYTHON_WORKER_METRICS_PATH="$MELIX_RUNTIME_DIR/python-worker-metrics-${RUN_TOKEN}.json"',
            'export MELIX_MENU_BAR_STARTUP_SURFACE="console"',
            f'export MELIX_MENU_BAR_PRESENTATION_MODE="{menu_bar_presentation_mode}"',
            f'export MELIX_PYTHON_BRIDGE_EXECUTABLE="$RESOURCES_DIR/{bundled_python_executable_relative_path}"',
            'export PYTHONUNBUFFERED=1',
            f'export PYTHONPATH="$RESOURCES_DIR/{bundled_site_packages_relative_path}:$MELIX_REPO_ROOT:$MELIX_REPO_ROOT/services/mlx-worker-python"',
            'cleanup() {',
            '  status=$?',
            '  [[ -n "${MELIX_SWIFT_WORKER_PID:-}" ]] && kill "$MELIX_SWIFT_WORKER_PID" >/dev/null 2>&1 || true',
            '  [[ -n "${MELIX_PYTHON_WORKER_PID:-}" ]] && kill "$MELIX_PYTHON_WORKER_PID" >/dev/null 2>&1 || true',
            '  rm -f "$MELIX_WORKER_SOCKET_PATH" "$MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"',
            '  exit $status',
            '}',
            'trap cleanup EXIT INT TERM',
            f'"$RESOURCES_DIR/{bundled_swift_worker_binary_name}" >"$MELIX_LOGS_DIR/swift-text-worker.stdout.log" 2>"$MELIX_LOGS_DIR/swift-text-worker.stderr.log" &',
            'MELIX_SWIFT_WORKER_PID=$!',
            'export MELIX_SWIFT_WORKER_PID',
            f'"$RESOURCES_DIR/{bundled_python_executable_relative_path}" -m worker.bootstrap --socket-path "$MELIX_WORKER_SOCKET_PATH" --backend-mode "$MELIX_BACKEND_MODE" >"$MELIX_LOGS_DIR/python-worker.stdout.log" 2>"$MELIX_LOGS_DIR/python-worker.stderr.log" &',
            'MELIX_PYTHON_WORKER_PID=$!',
            'export MELIX_PYTHON_WORKER_PID',
            f'"$RESOURCES_DIR/{bundled_python_executable_relative_path}" "$RESOURCES_DIR/{wait_script_relative_path}" --socket-path "$MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH" --timeout-seconds 30',
            f'"$RESOURCES_DIR/{bundled_python_executable_relative_path}" "$RESOURCES_DIR/{wait_script_relative_path}" --socket-path "$MELIX_WORKER_SOCKET_PATH" --timeout-seconds 30',
            f'exec "$RESOURCES_DIR/{bundled_app_binary_name}" "$@"',
            "",
        ]
    )


def write_unsigned_macos_app_bundle(
    *,
    repo_root: str | Path,
    executable_path: str | Path,
    cli_executable_path: str | Path,
    swift_text_worker_executable_path: str | Path,
    python_runtime_root: str | Path,
    python_site_packages_path: str | Path,
    output_path: str | Path,
    app_name: str = "Melix",
    bundle_id: str = "io.melix.menubar.preview",
    version: str = "0.1.0",
    packaging_target_id: str = "macos_app_bundle_preview",
    update_channel_path: str | Path | None = None,
    icon_source_path: str | Path | None = None,
) -> dict[str, str]:
    repo_root_path = Path(repo_root).expanduser().resolve()
    executable = Path(executable_path).expanduser().resolve()
    cli_executable = Path(cli_executable_path).expanduser().resolve()
    swift_worker_executable = Path(swift_text_worker_executable_path).expanduser().resolve()
    python_runtime = Path(python_runtime_root).expanduser().resolve()
    python_site_packages = Path(python_site_packages_path).expanduser().resolve()
    resolved_update_channel_path = (
        Path(update_channel_path).expanduser().resolve()
        if update_channel_path is not None
        else default_update_channel_path(repo_root_path)
    )
    resolved_icon_source_path = (
        Path(icon_source_path).expanduser().resolve()
        if icon_source_path is not None
        else repo_root_path / "apps/macos-menubar/Sources/AppMain/Resources/Branding/MelixAppIcon.icns"
    )

    if not executable.is_file():
        raise FileNotFoundError(f"Missing menubar executable: {executable}")
    if not cli_executable.is_file():
        raise FileNotFoundError(f"Missing Melix CLI executable: {cli_executable}")
    if not swift_worker_executable.is_file():
        raise FileNotFoundError(f"Missing Swift text worker executable: {swift_worker_executable}")
    if not python_runtime.is_dir():
        raise FileNotFoundError(f"Missing bundled Python runtime root: {python_runtime}")
    if not python_site_packages.is_dir():
        raise FileNotFoundError(f"Missing Python site-packages: {python_site_packages}")
    if not resolved_icon_source_path.is_file():
        raise FileNotFoundError(f"Missing macOS app icon: {resolved_icon_source_path}")

    layout = build_macos_app_bundle_layout(output_path, app_name=app_name)
    target_metadata = build_packaging_target_metadata(
        packaging_target_id,
        product_version=version,
        update_channel_path=resolved_update_channel_path,
        bundle_id=bundle_id,
    )
    if layout.app_path.exists():
        shutil.rmtree(layout.app_path)

    layout.macos_path.mkdir(parents=True, exist_ok=True)
    layout.resources_path.mkdir(parents=True, exist_ok=True)

    shutil.copy2(executable, layout.bundled_app_binary_path)
    shutil.copy2(cli_executable, layout.bundled_cli_binary_path)
    shutil.copy2(swift_worker_executable, layout.bundled_swift_worker_binary_path)
    shutil.copy2(resolved_icon_source_path, layout.bundled_icon_path)
    shutil.copytree(python_runtime, layout.bundled_python_runtime_path, dirs_exist_ok=True, symlinks=True)
    shutil.copytree(python_site_packages, layout.bundled_site_packages_path, dirs_exist_ok=True, symlinks=True)

    _copy_repo_subset(repo_root_path, layout.bundled_repo_root_path)

    layout.embedded_env_script_path.write_text(
        render_portable_environment_script(
            product_version=version,
            update_channel_path=resolved_update_channel_path,
            logical_product_identity=str(target_metadata["logical_product_identity"]),
            packaging_target_id=str(target_metadata["packaging_target_id"]),
            packaging_kind=str(target_metadata["packaging_kind"]),
        ),
        encoding="utf-8",
    )
    os.chmod(layout.embedded_env_script_path, 0o755)
    layout.packaging_target_manifest_path.write_text(
        json.dumps(target_metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    layout.plist_path.write_bytes(
        render_info_plist(
            app_name=app_name,
            bundle_id=bundle_id,
            version=version,
            icon_file=layout.bundled_icon_path.name,
        )
    )
    layout.launcher_path.write_text(
        render_launcher_script(
            app_name=app_name,
            bundle_repo_root=Path("repo"),
            bundled_app_binary_name=layout.bundled_app_binary_path.name,
            bundled_cli_binary_name=layout.bundled_cli_binary_path.name,
            bundled_swift_worker_binary_name=layout.bundled_swift_worker_binary_path.name,
            bundled_python_executable_relative_path=layout.bundled_python_executable_path.relative_to(layout.resources_path).as_posix(),
            bundled_site_packages_relative_path=layout.bundled_site_packages_path.relative_to(layout.resources_path).as_posix(),
            wait_script_relative_path=layout.bundled_wait_script_path.relative_to(layout.resources_path).as_posix(),
        ),
        encoding="utf-8",
    )

    for path in (
        layout.launcher_path,
        layout.bundled_app_binary_path,
        layout.bundled_cli_binary_path,
        layout.bundled_swift_worker_binary_path,
        layout.bundled_python_executable_path,
    ):
        os.chmod(path, 0o755)

    return {
        "app_path": str(layout.app_path),
        "launcher_path": str(layout.launcher_path),
        "resources_path": str(layout.resources_path),
        "bundled_binary_path": str(layout.bundled_app_binary_path),
        "bundled_cli_binary_path": str(layout.bundled_cli_binary_path),
        "bundled_swift_worker_binary_path": str(layout.bundled_swift_worker_binary_path),
        "bundled_python_runtime_path": str(layout.bundled_python_runtime_path),
        "bundled_site_packages_path": str(layout.bundled_site_packages_path),
        "bundled_repo_root_path": str(layout.bundled_repo_root_path),
        "bundled_icon_path": str(layout.bundled_icon_path),
        "plist_path": str(layout.plist_path),
        "embedded_env_script_path": str(layout.embedded_env_script_path),
        "packaging_target_manifest_path": str(layout.packaging_target_manifest_path),
        "bundle_id": bundle_id,
        "version": version,
        "packaging_target_id": str(target_metadata["packaging_target_id"]),
        "packaging_kind": str(target_metadata["packaging_kind"]),
        "logical_product_identity": str(target_metadata["logical_product_identity"]),
        "update_channel_path": str(target_metadata["update_channel_path"]),
    }


def archive_macos_app_bundle(app_path: str | Path, archive_path: str | Path) -> Path:
    app = Path(app_path).expanduser().resolve()
    archive = Path(archive_path).expanduser().resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["COPYFILE_DISABLE"] = "1"
    subprocess.run(
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--norsrc",
            "--keepParent",
            os.fspath(app),
            os.fspath(archive),
        ],
        check=True,
        env=environment,
    )
    return archive


def _copy_repo_subset(repo_root: Path, target_root: Path) -> None:
    worker_root = target_root / "services/mlx-worker-python"
    protocol_root = target_root / "packages/protocol/python"
    scripts_root = target_root / "scripts"
    evaluation_fixtures_root = worker_root / "fixtures/evaluation"

    (worker_root / "worker").mkdir(parents=True, exist_ok=True)
    protocol_root.mkdir(parents=True, exist_ok=True)
    scripts_root.mkdir(parents=True, exist_ok=True)
    evaluation_fixtures_root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        repo_root / "services/mlx-worker-python/worker",
        worker_root / "worker",
        dirs_exist_ok=True,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(repo_root / "services/mlx-worker-python/pyproject.toml", worker_root / "pyproject.toml")
    shutil.copytree(
        repo_root / "packages/protocol/python",
        protocol_root,
        dirs_exist_ok=True,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for dataset_id in _BUNDLED_EVALUATION_FIXTURE_IDS:
        source_root = repo_root / "services/mlx-worker-python/fixtures/evaluation" / dataset_id
        if not source_root.is_dir():
            continue
        shutil.copytree(
            source_root,
            evaluation_fixtures_root / dataset_id,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copy2(repo_root / "scripts/wait_for_worker_ready.py", scripts_root / "wait_for_worker_ready.py")
