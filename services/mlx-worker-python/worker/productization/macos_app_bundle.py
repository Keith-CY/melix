from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.productization.packaging_targets import (
    build_packaging_target_metadata,
    format_http_url_host,
    resolve_local_connect_host,
)
from worker.productization.startup_signals import default_update_channel_path


_BUNDLED_EVALUATION_FIXTURE_IDS = ("top200.event-extraction.top20.v1",)
_BUNDLED_BENCHMARK_FIXTURE_IDS = (
    "agentic-image.dev.v1",
    "agentic-search.dev.v1",
    "agentic-visit.dev.v1",
)
_PRUNABLE_PYTHON_PACKAGE_DIR_NAMES = frozenset(
    ("__pycache__", "doc", "docs", "test", "testing", "tests")
)
_PRUNABLE_PYTHON_RUNTIME_DIR_NAMES = frozenset(("__pycache__", "ensurepip"))
_PRUNABLE_PYTHON_RUNTIME_FILE_SUFFIXES = frozenset((".a", ".pyc"))
_PYTHON_NATIVE_BINARY_SUFFIXES = (".dylib", ".so")
_PYTHON_RUNTIME_EXECUTABLE_NAMES = frozenset(("python", "python3"))
_MACHO_MAGIC_VALUES = frozenset(
    (
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    )
)


@dataclass(frozen=True)
class MacOSAppBundleLayout:
    app_path: Path
    contents_path: Path
    macos_path: Path
    resources_path: Path
    plist_path: Path
    launcher_path: Path
    launcher_script_path: Path
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
        launcher_script_path=resources_path / f"{app_name}.sh",
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


def _reject_external_python_framework_runtime(python_runtime: str | Path) -> None:
    runtime_root = Path(python_runtime).expanduser().resolve()
    python_executable = runtime_root / "bin/python3"
    if not python_executable.is_file():
        raise FileNotFoundError(f"Missing bundled Python executable: {python_executable}")
    try:
        result = subprocess.run(
            ["otool", "-L", os.fspath(python_executable)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return
    external_framework_prefix = "/Library/Frameworks/Python.framework/"
    if external_framework_prefix in result.stdout:
        raise ValueError(
            "Bundled Python runtime links to an external Python framework. "
            f"Use a relocatable Python runtime instead: {python_executable}"
        )


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
    http_bind_host: str = "127.0.0.1",
    http_connect_host: str = "127.0.0.1",
    http_port: int = 12436,
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
            'export MELIX_HOME="${MELIX_HOME:-$HOME/.melix}"',
            'export MELIX_RUNTIME_DIR="${MELIX_RUNTIME_DIR:-$MELIX_HOME/run}"',
            'export MELIX_MANAGED_MODEL_ROOT="${MELIX_MANAGED_MODEL_ROOT:-$MELIX_HOME/models/default-managed}"',
            'export MELIX_AUDIO_RUNTIME_PACK_ROOT="${MELIX_AUDIO_RUNTIME_PACK_ROOT:-$MELIX_HOME/runtime-packs/audio}"',
            'export MELIX_MODEL_OPS_JOBS_ROOT="${MELIX_MODEL_OPS_JOBS_ROOT:-$MELIX_HOME/jobs/model-ops}"',
            'export MELIX_EVALUATION_JOBS_ROOT="${MELIX_EVALUATION_JOBS_ROOT:-$MELIX_HOME/jobs/evaluation}"',
            'export MELIX_GATEWAY_CONFIG_STORE_PATH="${MELIX_GATEWAY_CONFIG_STORE_PATH:-$MELIX_HOME/config/gateway-config.json}"',
            'export MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH="${MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH:-$MELIX_HOME/config/gateway-serving-defaults.json}"',
            'export MELIX_IMAGE_DEFAULTS_STORE_PATH="${MELIX_IMAGE_DEFAULTS_STORE_PATH:-$MELIX_HOME/config/image-defaults.json}"',
            'export MELIX_PRODUCT_MANIFEST_PATH="${MELIX_PRODUCT_MANIFEST_PATH:-$MELIX_HOME/install/install-manifest.json}"',
            f'export MELIX_HTTP_HOST="${{MELIX_HTTP_HOST:-{http_bind_host}}}"',
            f'export MELIX_HTTP_CONNECT_HOST="${{MELIX_HTTP_CONNECT_HOST:-{http_connect_host}}}"',
            f'export MELIX_HTTP_PORT="${{MELIX_HTTP_PORT:-{http_port}}}"',
            'export MELIX_BACKEND_MODE="auto"',
            'export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="swift"',
            'export MELIX_LOGS_DIR="${MELIX_LOGS_DIR:-$MELIX_HOME/logs}"',
            'export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$MELIX_RUNTIME_DIR/python-bytecode-cache}"',
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
            'mkdir -p "$MELIX_HOME/config" "$MELIX_HOME/state" "$MELIX_HOME/secrets" "$MELIX_HOME/install" "$MELIX_RUNTIME_DIR" "$MELIX_LOGS_DIR" "$MELIX_RUNTIME_DIR/swift-text-worker-cache" "$MELIX_RUNTIME_DIR/python-bytecode-cache" "$MELIX_MANAGED_MODEL_ROOT" "$MELIX_AUDIO_RUNTIME_PACK_ROOT" "$MELIX_MODEL_OPS_JOBS_ROOT" "$MELIX_EVALUATION_JOBS_ROOT"',
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


def render_native_launcher_source(*, script_relative_path: str) -> str:
    return "\n".join(
        [
            "#include <limits.h>",
            "#include <mach-o/dyld.h>",
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "#include <string.h>",
            "#include <unistd.h>",
            "",
            "int main(int argc, char *argv[]) {",
            "    uint32_t executablePathSize = PATH_MAX;",
            "    char executablePath[PATH_MAX];",
            "    if (_NSGetExecutablePath(executablePath, &executablePathSize) != 0) {",
            '        fputs("Unable to resolve Melix launcher path.\\n", stderr);',
            "        return 127;",
            "    }",
            "    char *lastSlash = strrchr(executablePath, '/');",
            "    if (lastSlash == NULL) {",
            '        fputs("Unable to resolve Melix launcher directory.\\n", stderr);',
            "        return 127;",
            "    }",
            "    *lastSlash = '\\0';",
            "    char scriptPath[PATH_MAX];",
            (
                f'    int written = snprintf(scriptPath, sizeof(scriptPath), "%s/{script_relative_path}", '
                "executablePath);"
            ),
            "    if (written < 0 || written >= (int)sizeof(scriptPath)) {",
            '        fputs("Melix launcher script path is too long.\\n", stderr);',
            "        return 127;",
            "    }",
            "    char **scriptArgv = calloc((size_t)argc + 2, sizeof(char *));",
            "    if (scriptArgv == NULL) {",
            '        fputs("Unable to allocate Melix launcher argv.\\n", stderr);',
            "        return 127;",
            "    }",
            '    scriptArgv[0] = "/bin/bash";',
            "    scriptArgv[1] = scriptPath;",
            "    for (int index = 1; index < argc; index += 1) {",
            "        scriptArgv[index + 1] = argv[index];",
            "    }",
            "    scriptArgv[argc + 1] = NULL;",
            '    execv("/bin/bash", scriptArgv);',
            '    perror("execv /bin/bash Melix launcher script");',
            "    return 127;",
            "}",
            "",
        ]
    )


def compile_native_launcher(source_path: Path, output_path: Path) -> None:
    xcrun = shutil.which("xcrun")
    if xcrun is None:
        raise FileNotFoundError("Unable to find xcrun for compiling the native macOS app launcher.")
    subprocess.run(
        [
            xcrun,
            "clang",
            "-Os",
            str(source_path),
            "-o",
            str(output_path),
        ],
        check=True,
    )


def elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 6)


def _path_size_bytes(path: Path) -> int:
    try:
        if path.is_symlink() or path.is_file():
            return path.lstat().st_size
    except OSError:
        return 0

    total = 0
    for root, dirnames, filenames in os.walk(path, followlinks=False):
        root_path = Path(root)
        for dirname in list(dirnames):
            directory = root_path / dirname
            try:
                if directory.is_symlink():
                    total += directory.lstat().st_size
                    dirnames.remove(dirname)
            except OSError:
                continue
        for filename in filenames:
            file_path = root_path / filename
            try:
                total += file_path.lstat().st_size
            except OSError:
                continue
    return total


def _prune_python_package_baggage(site_packages: Path) -> dict[str, int]:
    result = {
        "directories_pruned": 0,
        "bytes_saved": 0,
    }
    for root, dirnames, _filenames in os.walk(site_packages, followlinks=False):
        root_path = Path(root)
        for dirname in list(dirnames):
            if dirname not in _PRUNABLE_PYTHON_PACKAGE_DIR_NAMES:
                continue
            target = root_path / dirname
            try:
                bytes_saved = _path_size_bytes(target)
                if target.is_symlink():
                    target.unlink()
                else:
                    shutil.rmtree(target)
            except OSError:
                dirnames.remove(dirname)
                continue
            result["bytes_saved"] += bytes_saved
            result["directories_pruned"] += 1
            dirnames.remove(dirname)
    return result


def _prune_python_runtime_baggage(python_runtime: Path) -> dict[str, int]:
    result = {
        "directories_pruned": 0,
        "files_pruned": 0,
        "bytes_saved": 0,
    }

    include_path = python_runtime / "include"
    if include_path.exists() or include_path.is_symlink():
        try:
            bytes_saved = _path_size_bytes(include_path)
            if include_path.is_symlink():
                include_path.unlink()
            else:
                shutil.rmtree(include_path)
        except OSError:
            pass
        else:
            result["bytes_saved"] += bytes_saved
            result["directories_pruned"] += 1

    for root, dirnames, filenames in os.walk(python_runtime, followlinks=False):
        root_path = Path(root)
        for dirname in list(dirnames):
            if dirname not in _PRUNABLE_PYTHON_RUNTIME_DIR_NAMES:
                continue
            target = root_path / dirname
            try:
                bytes_saved = _path_size_bytes(target)
                if target.is_symlink():
                    target.unlink()
                else:
                    shutil.rmtree(target)
            except OSError:
                dirnames.remove(dirname)
                continue
            result["bytes_saved"] += bytes_saved
            result["directories_pruned"] += 1
            dirnames.remove(dirname)
        for filename in filenames:
            target = root_path / filename
            if target.suffix not in _PRUNABLE_PYTHON_RUNTIME_FILE_SUFFIXES:
                continue
            try:
                result["bytes_saved"] += target.lstat().st_size
                target.unlink()
            except OSError:
                continue
            result["files_pruned"] += 1
    return result


def _iter_python_native_binary_candidates(
    python_runtime_path: Path,
    site_packages_path: Path,
) -> list[Path]:
    def collect(root_path: Path, *, include_runtime_executables: bool) -> list[Path]:
        selected: list[Path] = []
        stack = [root_path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
            except OSError:
                continue
            include_current_runtime_executables = include_runtime_executables and current.name == "bin"
            for entry in reversed(entries):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                        continue
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entry.name.endswith(_PYTHON_NATIVE_BINARY_SUFFIXES):
                    selected.append(Path(entry.path))
                    continue
                if not include_current_runtime_executables:
                    continue
                if entry.name in _PYTHON_RUNTIME_EXECUTABLE_NAMES or entry.name.startswith("python3."):
                    selected.append(Path(entry.path))
        return selected

    candidates = collect(python_runtime_path, include_runtime_executables=True)
    candidates.extend(collect(site_packages_path, include_runtime_executables=False))
    return candidates


def _strip_packaged_binaries(paths: list[Path]) -> dict[str, int | bool]:
    strip = shutil.which("strip")
    result: dict[str, int | bool] = {
        "strip_available": strip is not None,
        "attempted": 0,
        "stripped": 0,
        "failed": 0,
        "bytes_saved": 0,
    }
    if strip is None:
        return result

    seen_targets: set[Path] = set()
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            target_key = path.resolve(strict=True)
        except OSError:
            continue
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)

        try:
            before_size = path.stat().st_size
        except OSError:
            continue
        result["attempted"] = int(result["attempted"]) + 1
        try:
            subprocess.run(
                [strip, "-x", os.fspath(path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            result["failed"] = int(result["failed"]) + 1
            continue
        result["stripped"] = int(result["stripped"]) + 1
        try:
            after_size = path.stat().st_size
        except OSError:
            after_size = before_size
        result["bytes_saved"] = int(result["bytes_saved"]) + max(0, before_size - after_size)
    return result


def _is_macho_file(path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        with path.open("rb") as handle:
            return handle.read(4) in _MACHO_MAGIC_VALUES
    except OSError:
        return False


def _iter_nested_macho_signing_targets(app_path: Path) -> list[Path]:
    targets: list[Path] = []
    stack = [app_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in reversed(entries):
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            path = Path(entry.path)
            if _is_macho_file(path):
                targets.append(path)
    targets.sort(key=lambda candidate: candidate.as_posix())
    return targets


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
    http_bind_host: str = "127.0.0.1",
    http_port: int = 12436,
) -> dict[str, Any]:
    write_started_at = time.perf_counter()
    timings: dict[str, float] = {}
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
    normalized_bind_host = http_bind_host.strip() or "127.0.0.1"
    resolved_connect_host = resolve_local_connect_host(normalized_bind_host)

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
    _reject_external_python_framework_runtime(python_runtime)

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

    started_at = time.perf_counter()
    shutil.copy2(executable, layout.bundled_app_binary_path)
    timings["copy_app_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(cli_executable, layout.bundled_cli_binary_path)
    timings["copy_cli_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(swift_worker_executable, layout.bundled_swift_worker_binary_path)
    timings["copy_swift_worker_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(resolved_icon_source_path, layout.bundled_icon_path)
    timings["copy_icon_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copytree(python_runtime, layout.bundled_python_runtime_path, dirs_exist_ok=True, symlinks=True)
    timings["copy_python_runtime_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copytree(python_site_packages, layout.bundled_site_packages_path, dirs_exist_ok=True, symlinks=True)
    timings["copy_python_site_packages_seconds"] = elapsed_seconds(started_at)

    started_at = time.perf_counter()
    swift_strip_result = _strip_packaged_binaries(
        [
            layout.bundled_app_binary_path,
            layout.bundled_cli_binary_path,
            layout.bundled_swift_worker_binary_path,
        ]
    )
    timings["strip_swift_binaries_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    python_prune_result = _prune_python_package_baggage(layout.bundled_site_packages_path)
    timings["prune_python_package_baggage_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    python_runtime_prune_result = _prune_python_runtime_baggage(layout.bundled_python_runtime_path)
    timings["prune_python_runtime_baggage_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    python_strip_result = _strip_packaged_binaries(
        _iter_python_native_binary_candidates(
            layout.bundled_python_runtime_path,
            layout.bundled_site_packages_path,
        )
    )
    timings["strip_python_native_binaries_seconds"] = elapsed_seconds(started_at)
    slimming = {
        "strip_available": bool(
            swift_strip_result["strip_available"] and python_strip_result["strip_available"]
        ),
        "swift_binaries_stripped": int(swift_strip_result["stripped"]),
        "swift_strip_failures": int(swift_strip_result["failed"]),
        "swift_strip_bytes_saved": int(swift_strip_result["bytes_saved"]),
        "python_native_binaries_stripped": int(python_strip_result["stripped"]),
        "python_native_strip_failures": int(python_strip_result["failed"]),
        "python_native_strip_bytes_saved": int(python_strip_result["bytes_saved"]),
        "python_package_directories_pruned": int(python_prune_result["directories_pruned"]),
        "python_package_baggage_bytes_saved": int(python_prune_result["bytes_saved"]),
        "python_runtime_directories_pruned": int(python_runtime_prune_result["directories_pruned"]),
        "python_runtime_files_pruned": int(python_runtime_prune_result["files_pruned"]),
        "python_runtime_baggage_bytes_saved": int(python_runtime_prune_result["bytes_saved"]),
        "bytes_saved": (
            int(swift_strip_result["bytes_saved"])
            + int(python_strip_result["bytes_saved"])
            + int(python_prune_result["bytes_saved"])
            + int(python_runtime_prune_result["bytes_saved"])
        ),
    }

    started_at = time.perf_counter()
    bundled_resource_bundle_paths = _copy_swiftpm_resource_bundles(
        executable.parent,
        [layout.resources_path],
    )
    timings["copy_swiftpm_resource_bundles_seconds"] = elapsed_seconds(started_at)

    started_at = time.perf_counter()
    _copy_repo_subset(repo_root_path, layout.bundled_repo_root_path)
    timings["copy_repo_subset_seconds"] = elapsed_seconds(started_at)

    started_at = time.perf_counter()
    layout.embedded_env_script_path.write_text(
        render_portable_environment_script(
            product_version=version,
            update_channel_path=resolved_update_channel_path,
            logical_product_identity=str(target_metadata["logical_product_identity"]),
            packaging_target_id=str(target_metadata["packaging_target_id"]),
            packaging_kind=str(target_metadata["packaging_kind"]),
            http_bind_host=normalized_bind_host,
            http_connect_host=resolved_connect_host,
            http_port=http_port,
        ),
        encoding="utf-8",
    )
    target_metadata["http_bind_host"] = normalized_bind_host
    target_metadata["http_connect_host"] = resolved_connect_host
    target_metadata["http_port"] = http_port
    target_metadata["health_probe_url"] = f"http://{format_http_url_host(resolved_connect_host)}:{http_port}/health"
    target_metadata["service_base_url"] = f"http://{format_http_url_host(resolved_connect_host)}:{http_port}/v1"
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
    layout.launcher_script_path.write_text(
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
    timings["write_metadata_seconds"] = elapsed_seconds(started_at)

    started_at = time.perf_counter()
    native_launcher_source_path = layout.macos_path / f"{app_name}Launcher.c"
    native_launcher_source_path.write_text(
        render_native_launcher_source(
            script_relative_path=f"../Resources/{layout.launcher_script_path.name}"
        ),
        encoding="utf-8",
    )
    try:
        compile_native_launcher(native_launcher_source_path, layout.launcher_path)
    finally:
        native_launcher_source_path.unlink(missing_ok=True)
    timings["compile_launcher_seconds"] = elapsed_seconds(started_at)

    started_at = time.perf_counter()
    os.chmod(layout.embedded_env_script_path, 0o755)
    for path in (
        layout.launcher_path,
        layout.bundled_app_binary_path,
        layout.bundled_cli_binary_path,
        layout.bundled_swift_worker_binary_path,
        layout.bundled_python_executable_path,
    ):
        os.chmod(path, 0o755)
    timings["chmod_seconds"] = elapsed_seconds(started_at)
    timings["write_total_seconds"] = elapsed_seconds(write_started_at)

    return {
        "app_path": str(layout.app_path),
        "launcher_path": str(layout.launcher_path),
        "launcher_script_path": str(layout.launcher_script_path),
        "resources_path": str(layout.resources_path),
        "bundled_binary_path": str(layout.bundled_app_binary_path),
        "bundled_cli_binary_path": str(layout.bundled_cli_binary_path),
        "bundled_swift_worker_binary_path": str(layout.bundled_swift_worker_binary_path),
        "bundled_python_runtime_path": str(layout.bundled_python_runtime_path),
        "bundled_site_packages_path": str(layout.bundled_site_packages_path),
        "bundled_repo_root_path": str(layout.bundled_repo_root_path),
        "bundled_icon_path": str(layout.bundled_icon_path),
        "bundled_swiftpm_resource_bundle_paths": [
            str(path) for path in bundled_resource_bundle_paths
        ],
        "plist_path": str(layout.plist_path),
        "embedded_env_script_path": str(layout.embedded_env_script_path),
        "packaging_target_manifest_path": str(layout.packaging_target_manifest_path),
        "bundle_id": bundle_id,
        "version": version,
        "packaging_target_id": str(target_metadata["packaging_target_id"]),
        "packaging_kind": str(target_metadata["packaging_kind"]),
        "logical_product_identity": str(target_metadata["logical_product_identity"]),
        "update_channel_path": str(target_metadata["update_channel_path"]),
        "http_bind_host": normalized_bind_host,
        "http_connect_host": resolved_connect_host,
        "http_port": http_port,
        "health_probe_url": str(target_metadata["health_probe_url"]),
        "service_base_url": str(target_metadata["service_base_url"]),
        "slimming": slimming,
        "timings": timings,
    }


def _copy_swiftpm_resource_bundles(source_root: Path, target_roots: list[Path]) -> list[Path]:
    copied_paths: list[Path] = []
    try:
        with os.scandir(source_root) as entries:
            bundle_names = []
            for entry in entries:
                if not entry.name.endswith(".bundle"):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                bundle_names.append(entry.name)
            bundle_names.sort()
    except OSError:
        return copied_paths

    for bundle_name in bundle_names:
        source = source_root / bundle_name
        for target_root in target_roots:
            target = target_root / bundle_name
            backup = target.with_name(f"{target.name}.melix-backup")
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.rename(backup)
            try:
                shutil.copytree(source, target, symlinks=True)
            except Exception:
                if target.exists():
                    shutil.rmtree(target)
                if backup.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            copied_paths.append(target)
    return copied_paths


def adhoc_sign_macos_app_bundle(app_path: str | Path) -> bool:
    app = Path(app_path).expanduser().resolve()
    codesign = shutil.which("codesign")
    if codesign is None:
        return False

    try:
        for nested_target in _iter_nested_macho_signing_targets(app):
            subprocess.run(
                [
                    codesign,
                    "--force",
                    "--sign",
                    "-",
                    os.fspath(nested_target),
                ],
                check=True,
            )
        subprocess.run(
            [
                codesign,
                "--force",
                "--deep",
                "--sign",
                "-",
                os.fspath(app),
            ],
            check=True,
        )
        subprocess.run(
            [
                codesign,
                "--verify",
                "--deep",
                "--strict",
                "--verbose=4",
                os.fspath(app),
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


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
    benchmark_fixtures_root = worker_root / "fixtures/benchmark"

    (worker_root / "worker").mkdir(parents=True, exist_ok=True)
    protocol_root.mkdir(parents=True, exist_ok=True)
    scripts_root.mkdir(parents=True, exist_ok=True)
    evaluation_fixtures_root.mkdir(parents=True, exist_ok=True)
    benchmark_fixtures_root.mkdir(parents=True, exist_ok=True)

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
    for fixture_package_id in _BUNDLED_BENCHMARK_FIXTURE_IDS:
        source_root = repo_root / "services/mlx-worker-python/fixtures/benchmark" / fixture_package_id
        if not source_root.is_dir():
            continue
        shutil.copytree(
            source_root,
            benchmark_fixtures_root / fixture_package_id,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    _copy_packaged_script(repo_root, scripts_root, "wait_for_worker_ready.py")


def _copy_packaged_script(repo_root: Path, target_scripts_root: Path, script_name: str) -> None:
    if script_name.endswith("_probe.py") or script_name.startswith("pr_scoped_performance_"):
        raise ValueError(f"CI-only probe script must not be packaged: {script_name}")
    shutil.copy2(repo_root / "scripts" / script_name, target_scripts_root / script_name)
