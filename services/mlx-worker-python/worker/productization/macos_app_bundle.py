from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from operator import itemgetter
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

from worker.productization.packaging_targets import (
    build_packaging_target_metadata,
    format_http_url_host,
    packaged_python_import_isolation_env_exports,
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
_SPARKLE_FEED_URL = "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
_SPARKLE_FRAMEWORK_RELATIVE_PATH = Path("Sparkle.framework")
_SPARKLE_EXECUTABLE_RPATH = "@loader_path/../Frameworks"
_CERTIFICATE_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_CERTIFICATE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACOS_PLATFORM_RE = re.compile(r"\.macOS\(\.v(?P<major>[1-9][0-9]*)\)")
_VERSIONED_PYTHON_EXECUTABLE_RE = re.compile(r"^python3\.[1-9][0-9]*$")
_RELEASE_BUNDLE_ID = "io.melix.menubar"
_RELEASE_PACKAGING_TARGET_ID = "macos_app_bundle_github_release"
_DISABLE_LIBRARY_VALIDATION_ENTITLEMENTS = {
    "com.apple.security.cs.disable-library-validation": True,
}
_DYNAMIC_CODE_HOST_RELATIVE_PATHS = frozenset(
    (
        Path("Contents/Resources/melix-menubar"),
        Path("Contents/Resources/melix-text-worker-swift"),
    )
)


@dataclass(frozen=True)
class MacOSAppBundleLayout:
    app_path: Path
    contents_path: Path
    macos_path: Path
    frameworks_path: Path
    resources_path: Path
    plist_path: Path
    launcher_path: Path
    launcher_script_path: Path
    bundled_app_binary_path: Path
    bundled_cli_binary_path: Path
    bundled_control_plane_binary_path: Path
    bundled_swift_worker_binary_path: Path
    bundled_swift_mlx_metallib_path: Path
    swift_mlx_metallib_link_path: Path
    bundled_python_runtime_path: Path
    bundled_python_executable_path: Path
    bundled_site_packages_path: Path
    bundled_repo_root_path: Path
    bundled_icon_path: Path
    bundled_sparkle_framework_path: Path
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
        frameworks_path=contents_path / "Frameworks",
        resources_path=resources_path,
        plist_path=contents_path / "Info.plist",
        launcher_path=macos_path / app_name,
        launcher_script_path=resources_path / f"{app_name}.sh",
        bundled_app_binary_path=resources_path / "melix-menubar",
        bundled_cli_binary_path=resources_path / "melix",
        bundled_control_plane_binary_path=resources_path / "melix-control-plane",
        bundled_swift_worker_binary_path=resources_path / "melix-text-worker-swift",
        bundled_swift_mlx_metallib_path=resources_path / "swift-mlx/mlx.metallib",
        swift_mlx_metallib_link_path=resources_path / "mlx.metallib",
        bundled_python_runtime_path=python_runtime_path,
        bundled_python_executable_path=python_runtime_path / "bin/python3",
        bundled_site_packages_path=resources_path / "python-site-packages",
        bundled_repo_root_path=resources_path / "repo",
        bundled_icon_path=resources_path / "MelixAppIcon.icns",
        bundled_sparkle_framework_path=contents_path / "Frameworks" / _SPARKLE_FRAMEWORK_RELATIVE_PATH,
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


def normalize_ats_insecure_http_hosts(hosts: Sequence[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for raw_host in hosts:
        host = raw_host.strip().lower().rstrip(".")
        if not host:
            raise ValueError("ATS insecure HTTP hosts must not be empty")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if address.version != 4:
                raise ValueError(
                    f"ATS insecure HTTP host currently supports IPv4 or DNS names, not IPv6: {raw_host}"
                )
            normalized.add(str(address))
            continue
        if any(character in host for character in ("/", ":", "@", "[", "]", "?", "#", "*")):
            raise ValueError(
                f"ATS insecure HTTP host must be a host without scheme, port, path, or wildcard: {raw_host}"
            )
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise ValueError(f"ATS insecure HTTP host is invalid: {raw_host}") from error
        labels = host.split(".")
        if len(host) > 253 or any(
            not label
            or len(label) > 63
            or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is None
            for label in labels
        ):
            raise ValueError(f"ATS insecure HTTP host is invalid: {raw_host}")
        normalized.add(host)
    return tuple(sorted(normalized))


def render_info_plist(
    *,
    app_name: str,
    bundle_id: str,
    version: str,
    icon_file: str,
    insecure_http_hosts: Sequence[str] = (),
    sparkle_feed_url: str | None = None,
    sparkle_public_ed_key: str | None = None,
    minimum_system_version: str = "15.0",
) -> bytes:
    ats_policy: dict[str, Any] = {
        "NSAllowsLocalNetworking": True,
    }
    normalized_insecure_http_hosts = normalize_ats_insecure_http_hosts(
        insecure_http_hosts
    )
    if normalized_insecure_http_hosts:
        ats_policy["NSExceptionDomains"] = {
            host: {
                "NSExceptionAllowsInsecureHTTPLoads": True,
            }
            for host in normalized_insecure_http_hosts
        }
    payload: dict[str, Any] = {
        "CFBundleDisplayName": app_name,
        "CFBundleExecutable": app_name,
        "CFBundleIconFile": icon_file,
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": minimum_system_version,
        "NSAppTransportSecurity": ats_policy,
        "NSHighResolutionCapable": True,
        "NSLocalNetworkUsageDescription": (
            "Connect to remote AI providers that you configure on your local network or tailnet."
        ),
    }
    update_configuration = normalize_sparkle_update_configuration(
        feed_url=sparkle_feed_url,
        public_ed_key=sparkle_public_ed_key,
    )
    if update_configuration is not None:
        payload.update(
            {
                "SUFeedURL": update_configuration["feed_url"],
                "SUPublicEDKey": update_configuration["public_ed_key"],
                "SUEnableAutomaticChecks": True,
                "SUAllowsAutomaticUpdates": False,
                "SUScheduledCheckInterval": 86_400,
                "SUVerifyUpdateBeforeExtraction": True,
                "SURequireSignedFeed": True,
            }
        )
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)


def resolve_macos_minimum_system_version(repo_root: str | Path) -> str:
    """Read the single macOS deployment target from the app Package.swift."""

    package_path = (
        Path(repo_root).expanduser().resolve() / "apps/macos-menubar/Package.swift"
    )
    source = package_path.read_text(encoding="utf-8")
    matches = _MACOS_PLATFORM_RE.findall(source)
    if len(matches) != 1:
        raise ValueError(
            "apps/macos-menubar/Package.swift must declare exactly one .macOS(.vN) platform"
        )
    return f"{int(matches[0])}.0"


def normalize_sparkle_update_configuration(
    *,
    feed_url: str | None,
    public_ed_key: str | None,
) -> dict[str, str] | None:
    normalized_feed_url = (feed_url or "").strip()
    normalized_public_key = (public_ed_key or "").strip()
    if not normalized_feed_url and not normalized_public_key:
        return None
    if not normalized_feed_url or not normalized_public_key:
        raise ValueError(
            "Sparkle feed URL and EdDSA public key must be provided together"
        )
    if normalized_feed_url != _SPARKLE_FEED_URL:
        raise ValueError(
            "Sparkle feed URL must use the stable signed Melix GitHub Releases feed"
        )
    try:
        decoded_key = base64.b64decode(normalized_public_key, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Sparkle EdDSA public key must be valid base64") from error
    if len(decoded_key) != 32:
        raise ValueError("Sparkle EdDSA public key must decode to exactly 32 bytes")
    return {
        "feed_url": normalized_feed_url,
        "public_ed_key": normalized_public_key,
    }


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
            'export MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY="environment"',
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
    bundled_control_plane_binary_name: str,
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
            'export MELIX_APP_BUNDLE_PATH="$(cd "$CONTENTS_DIR/.." && pwd)"',
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
            *packaged_python_import_isolation_env_exports(),  # pragma: no cover
            f'export PYTHONPATH="$RESOURCES_DIR/{bundled_site_packages_relative_path}:$MELIX_REPO_ROOT:$MELIX_REPO_ROOT/services/mlx-worker-python"',
            'cleanup() {',
            '  status=$?',
            '  [[ -n "${MELIX_ACTIVE_RUNTIME_PATH:-}" ]] && rm -f "$MELIX_ACTIVE_RUNTIME_PATH"',
            '  [[ -n "${MELIX_CONTROL_PLANE_PID:-}" ]] && kill "$MELIX_CONTROL_PLANE_PID" >/dev/null 2>&1 || true',
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
            (
                f'if "$RESOURCES_DIR/{bundled_python_executable_relative_path}" '
                '-c \'import socket, sys; connection = socket.create_connection((sys.argv[1], int(sys.argv[2])), 0.2); connection.close()\' '
                '"$MELIX_HTTP_CONNECT_HOST" "$MELIX_HTTP_PORT" >/dev/null 2>&1; then'
            ),
            '  printf "Melix HTTP port %s is already in use on %s.\\n" "$MELIX_HTTP_PORT" "$MELIX_HTTP_CONNECT_HOST" >&2',
            '  exit 1',
            'fi',
            f'"$RESOURCES_DIR/{bundled_control_plane_binary_name}" >"$MELIX_LOGS_DIR/control-plane.stdout.log" 2>"$MELIX_LOGS_DIR/control-plane.stderr.log" &',
            'MELIX_CONTROL_PLANE_PID=$!',
            'export MELIX_CONTROL_PLANE_PID',
            'MELIX_HTTP_READY_URL="http://$MELIX_HTTP_CONNECT_HOST:$MELIX_HTTP_PORT/health"',
            'MELIX_HTTP_READY=0',
            'for _ in {1..60}; do',
            '  if ! kill -0 "$MELIX_CONTROL_PLANE_PID" >/dev/null 2>&1; then',
            '    wait "$MELIX_CONTROL_PLANE_PID" >/dev/null 2>&1 || true',
            '    printf "Melix control plane exited before becoming ready. See %s/control-plane.stderr.log.\\n" "$MELIX_LOGS_DIR" >&2',
            '    exit 1',
            '  fi',
            '  if /usr/bin/curl --fail --silent --show-error "$MELIX_HTTP_READY_URL" >/dev/null 2>&1; then',
            '    sleep 0.1',
            '    if kill -0 "$MELIX_CONTROL_PLANE_PID" >/dev/null 2>&1; then',
            '      MELIX_HTTP_READY=1',
            '      break',
            '    fi',
            '  fi',
            '  sleep 0.5',
            'done',
            'if [[ "$MELIX_HTTP_READY" != "1" ]]; then',
            '  printf "Melix control plane did not become ready at %s. See %s/control-plane.stderr.log.\\n" "$MELIX_HTTP_READY_URL" "$MELIX_LOGS_DIR" >&2',
            '  exit 1',
            'fi',
            'export MELIX_ACTIVE_RUNTIME_PATH="${MELIX_ACTIVE_RUNTIME_PATH:-$MELIX_RUNTIME_DIR/active-runtime.json}"',
            (
                f'"$RESOURCES_DIR/{bundled_python_executable_relative_path}" '
                '-m worker.productization.active_runtime '
                '--output-path "$MELIX_ACTIVE_RUNTIME_PATH" '
                '--app-process-id "$$" '
                '--control-plane-process-id "$MELIX_CONTROL_PLANE_PID" '
                '--python-worker-process-id "$MELIX_PYTHON_WORKER_PID" '
                '--swift-text-worker-process-id "$MELIX_SWIFT_WORKER_PID" '
                '--python-worker-socket-path "$MELIX_WORKER_SOCKET_PATH" '
                '--swift-text-worker-socket-path "$MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH" '
                '--service-base-url "http://$MELIX_HTTP_CONNECT_HOST:$MELIX_HTTP_PORT/v1"'
            ),
            'MELIX_APP_PROCESS_PID=$$',
            'MELIX_WATCHDOG_CONTROL_PLANE_PID="$MELIX_CONTROL_PLANE_PID"',
            'MELIX_WATCHDOG_SWIFT_WORKER_PID="$MELIX_SWIFT_WORKER_PID"',
            'MELIX_WATCHDOG_PYTHON_WORKER_PID="$MELIX_PYTHON_WORKER_PID"',
            '(',
            '  while kill -0 "$MELIX_APP_PROCESS_PID" >/dev/null 2>&1; do',
            '    if [[ -n "$MELIX_WATCHDOG_CONTROL_PLANE_PID" ]] && ! kill -0 "$MELIX_WATCHDOG_CONTROL_PLANE_PID" >/dev/null 2>&1; then',
            '      MELIX_WATCHDOG_CONTROL_PLANE_PID=""',
            '    fi',
            '    if [[ -n "$MELIX_WATCHDOG_SWIFT_WORKER_PID" ]] && ! kill -0 "$MELIX_WATCHDOG_SWIFT_WORKER_PID" >/dev/null 2>&1; then',
            '      MELIX_WATCHDOG_SWIFT_WORKER_PID=""',
            '    fi',
            '    if [[ -n "$MELIX_WATCHDOG_PYTHON_WORKER_PID" ]] && ! kill -0 "$MELIX_WATCHDOG_PYTHON_WORKER_PID" >/dev/null 2>&1; then',
            '      MELIX_WATCHDOG_PYTHON_WORKER_PID=""',
            '    fi',
            '    /bin/sleep 0.25',
            '  done',
            '  rm -f "$MELIX_ACTIVE_RUNTIME_PATH"',
            '  [[ -n "$MELIX_WATCHDOG_CONTROL_PLANE_PID" ]] && kill "$MELIX_WATCHDOG_CONTROL_PLANE_PID" >/dev/null 2>&1 || true',
            '  [[ -n "$MELIX_WATCHDOG_SWIFT_WORKER_PID" ]] && kill "$MELIX_WATCHDOG_SWIFT_WORKER_PID" >/dev/null 2>&1 || true',
            '  [[ -n "$MELIX_WATCHDOG_PYTHON_WORKER_PID" ]] && kill "$MELIX_WATCHDOG_PYTHON_WORKER_PID" >/dev/null 2>&1 || true',
            '  rm -f "$MELIX_WORKER_SOCKET_PATH" "$MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"',
            ') >/dev/null 2>&1 &',
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
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _prune_python_package_baggage(site_packages: Path) -> dict[str, int]:
    result = {
        "directories_pruned": 0,
        "bytes_saved": 0,
    }
    stack = [site_packages]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue

                    if entry.name in _PRUNABLE_PYTHON_PACKAGE_DIR_NAMES:
                        target = Path(entry.path)
                        try:
                            bytes_saved = _path_size_bytes(target)
                            if entry.is_symlink():
                                target.unlink()
                            else:
                                shutil.rmtree(target)
                        except OSError:
                            continue
                        result["bytes_saved"] += bytes_saved
                        result["directories_pruned"] += 1
                        continue

                    if is_directory:
                        stack.append(Path(entry.path))
        except OSError:
            continue
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

    prunable_suffixes = tuple(_PRUNABLE_PYTHON_RUNTIME_FILE_SUFFIXES)
    stack: list[Path | str] = [python_runtime]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue

                    if entry.name in _PRUNABLE_PYTHON_RUNTIME_DIR_NAMES:
                        if not is_directory:
                            try:
                                if not entry.is_symlink():
                                    continue
                            except OSError:
                                continue
                        target = Path(entry.path)
                        try:
                            bytes_saved = _path_size_bytes(target)
                            if entry.is_symlink():
                                target.unlink()
                            else:
                                shutil.rmtree(target)
                        except OSError:
                            continue
                        result["bytes_saved"] += bytes_saved
                        result["directories_pruned"] += 1
                        continue

                    if is_directory:
                        stack.append(entry.path)
                        continue

                    if not entry.name.endswith(prunable_suffixes):
                        continue
                    try:
                        result["bytes_saved"] += entry.stat(follow_symlinks=False).st_size
                        os.unlink(entry.path)
                    except OSError:
                        continue
                    result["files_pruned"] += 1
        except OSError:
            continue
    return result


def _iter_python_native_binary_candidates(
    python_runtime_path: Path,
    site_packages_path: Path,
) -> list[Path]:
    def collect(root_path: Path, *, include_runtime_executables: bool) -> list[Path]:
        selected: list[Path] = []
        selected_append = selected.append
        stack = [os.fspath(root_path)]
        stack_append = stack.append
        stack_pop = stack.pop
        path_cls = Path
        scandir = os.scandir
        native_suffixes = _PYTHON_NATIVE_BINARY_SUFFIXES
        runtime_executable_names = _PYTHON_RUNTIME_EXECUTABLE_NAMES
        bin_path_suffix = f"{os.sep}bin"
        while stack:
            current = stack_pop()
            include_current_runtime_executables = include_runtime_executables and (
                current.endswith(bin_path_suffix) or current == "bin"
            )
            try:
                with scandir(current) as entries:
                    for entry in entries:
                        entry_name = entry.name
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                stack_append(entry.path)
                                continue
                            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        if entry_name.endswith(native_suffixes):
                            selected_append(path_cls(entry.path))
                            continue
                        if not include_current_runtime_executables:
                            continue
                        if entry_name in runtime_executable_names or entry_name.startswith("python3."):
                            selected_append(path_cls(entry.path))
            except OSError:
                continue
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


def _read_sparkle_framework_version(framework_path: Path) -> str:
    plist_path = framework_path / "Versions/B/Resources/Info.plist"
    if not plist_path.is_file():
        raise FileNotFoundError(f"Sparkle framework Info.plist is missing: {plist_path}")
    with plist_path.open("rb") as handle:
        payload = plistlib.load(handle)
    version = str(
        payload.get("CFBundleShortVersionString")
        or payload.get("CFBundleVersion")
        or ""
    ).strip()
    if not version:
        raise ValueError(f"Sparkle framework version is missing: {plist_path}")
    return version


def _ensure_sparkle_executable_rpath(executable_path: Path) -> bool:
    if not _is_macho_file(executable_path):
        return False
    otool = shutil.which("otool")
    install_name_tool = shutil.which("install_name_tool")
    if otool is None or install_name_tool is None:
        raise RuntimeError(
            "otool and install_name_tool are required to embed the Sparkle framework"
        )
    inspection = subprocess.run(
        [otool, "-l", os.fspath(executable_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    if _SPARKLE_EXECUTABLE_RPATH in inspection.stdout:
        return True
    subprocess.run(
        [
            install_name_tool,
            "-add_rpath",
            _SPARKLE_EXECUTABLE_RPATH,
            os.fspath(executable_path),
        ],
        check=True,
    )
    verification = subprocess.run(
        [otool, "-l", os.fspath(executable_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    if _SPARKLE_EXECUTABLE_RPATH not in verification.stdout:
        raise RuntimeError(
            f"Packaged menu-bar executable is missing {_SPARKLE_EXECUTABLE_RPATH}"
        )
    return True


def _iter_nested_macho_signing_targets(app_path: Path) -> list[Path]:
    targets: list[Path] = []
    stack = [app_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
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
        except OSError:
            continue
    targets.sort(key=lambda candidate: candidate.as_posix())
    return targets


def write_unsigned_macos_app_bundle(
    *,
    repo_root: str | Path,
    executable_path: str | Path,
    cli_executable_path: str | Path,
    control_plane_executable_path: str | Path,
    swift_text_worker_executable_path: str | Path,
    swift_mlx_metallib_path: str | Path,
    swift_mlx_metallib_version: str,
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
    insecure_http_hosts: Sequence[str] = (),
    sparkle_framework_path: str | Path | None = None,
    sparkle_feed_url: str | None = None,
    sparkle_public_ed_key: str | None = None,
    code_signing_mode: str = "adhoc",
    code_signing_certificate_sha256: str | None = None,
    code_signing_certificate_sha1: str | None = None,
    code_signing_authority: str | None = None,
    minimum_system_version: str = "15.0",
) -> dict[str, Any]:
    write_started_at = time.perf_counter()
    timings: dict[str, float] = {}
    repo_root_path = Path(repo_root).expanduser().resolve()
    if re.fullmatch(r"[1-9][0-9]*\.0", minimum_system_version) is None:
        raise ValueError("minimum system version must use MAJOR.0 format")
    executable = Path(executable_path).expanduser().resolve()
    cli_executable = Path(cli_executable_path).expanduser().resolve()
    control_plane_executable = Path(control_plane_executable_path).expanduser().resolve()
    swift_worker_executable = Path(swift_text_worker_executable_path).expanduser().resolve()
    swift_mlx_metallib = Path(swift_mlx_metallib_path).expanduser().resolve()
    normalized_swift_mlx_metallib_version = swift_mlx_metallib_version.strip()
    python_runtime = Path(python_runtime_root).expanduser().resolve()
    python_site_packages = Path(python_site_packages_path).expanduser().resolve()
    normalized_insecure_http_hosts = normalize_ats_insecure_http_hosts(
        insecure_http_hosts
    )
    sparkle_update_configuration = normalize_sparkle_update_configuration(
        feed_url=sparkle_feed_url,
        public_ed_key=sparkle_public_ed_key,
    )
    release_metadata = (
        bundle_id == _RELEASE_BUNDLE_ID
        and packaging_target_id == _RELEASE_PACKAGING_TARGET_ID
    )
    partial_release_metadata = (
        bundle_id == _RELEASE_BUNDLE_ID
        or packaging_target_id == _RELEASE_PACKAGING_TARGET_ID
    )
    if sparkle_update_configuration is not None and not release_metadata:
        raise ValueError(
            "Signed updates require the stable Melix release bundle ID and packaging target"
        )
    if sparkle_update_configuration is None and partial_release_metadata:
        raise ValueError(
            "The Melix release bundle identity must not be used without signed updates"
        )
    normalized_code_signing_mode = code_signing_mode.strip()
    normalized_code_signing_certificate_sha256 = (
        normalize_codesign_certificate_sha256(code_signing_certificate_sha256)
        if code_signing_certificate_sha256 is not None
        else None
    )
    normalized_code_signing_certificate_sha1 = (
        normalize_codesign_certificate_sha1(code_signing_certificate_sha1)
        if code_signing_certificate_sha1 is not None
        else None
    )
    normalized_code_signing_authority = (
        code_signing_authority.strip()
        if code_signing_authority is not None
        else None
    )
    if sparkle_update_configuration is None:
        if normalized_code_signing_mode != "adhoc":
            raise ValueError("Preview bundles require ad-hoc code signing")
        if (
            normalized_code_signing_certificate_sha256 is not None
            or normalized_code_signing_certificate_sha1 is not None
            or normalized_code_signing_authority is not None
        ):
            raise ValueError(
                "Preview bundles must not declare a release code-signing identity"
            )
    else:
        if normalized_code_signing_mode != "stable_self_signed":
            raise ValueError(
                "Signed updates require stable self-signed code-signing metadata"
            )
        if (
            normalized_code_signing_certificate_sha256 is None
            or normalized_code_signing_certificate_sha1 is None
            or not normalized_code_signing_authority
        ):
            raise ValueError(
                "Signed updates require independent release certificate SHA-256, SHA-1, and authority pins"
            )
    sparkle_framework = (
        Path(sparkle_framework_path).expanduser().resolve()
        if sparkle_framework_path is not None
        else None
    )
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
    if not control_plane_executable.is_file():
        raise FileNotFoundError(f"Missing Melix control-plane executable: {control_plane_executable}")
    if not swift_worker_executable.is_file():
        raise FileNotFoundError(f"Missing Swift text worker executable: {swift_worker_executable}")
    if not swift_mlx_metallib.is_file():
        raise FileNotFoundError(f"Missing Swift MLX metallib: {swift_mlx_metallib}")
    if not normalized_swift_mlx_metallib_version:
        raise ValueError("Swift MLX metallib version must not be empty")
    if not python_runtime.is_dir():
        raise FileNotFoundError(f"Missing bundled Python runtime root: {python_runtime}")
    if not python_site_packages.is_dir():
        raise FileNotFoundError(f"Missing Python site-packages: {python_site_packages}")
    if not resolved_icon_source_path.is_file():
        raise FileNotFoundError(f"Missing macOS app icon: {resolved_icon_source_path}")
    if sparkle_framework is not None and not sparkle_framework.is_dir():
        raise FileNotFoundError(f"Missing Sparkle framework: {sparkle_framework}")
    if sparkle_update_configuration is not None and sparkle_framework is None:
        raise ValueError("Signed updates require a packaged Sparkle framework")
    sparkle_framework_version = (
        _read_sparkle_framework_version(sparkle_framework)
        if sparkle_framework is not None
        else None
    )
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
    layout.frameworks_path.mkdir(parents=True, exist_ok=True)

    started_at = time.perf_counter()
    shutil.copy2(executable, layout.bundled_app_binary_path)
    timings["copy_app_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(cli_executable, layout.bundled_cli_binary_path)
    timings["copy_cli_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(control_plane_executable, layout.bundled_control_plane_binary_path)
    timings["copy_control_plane_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(swift_worker_executable, layout.bundled_swift_worker_binary_path)
    timings["copy_swift_worker_binary_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    layout.bundled_swift_mlx_metallib_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(swift_mlx_metallib, layout.bundled_swift_mlx_metallib_path)
    layout.swift_mlx_metallib_link_path.symlink_to(Path("swift-mlx/mlx.metallib"))
    if not layout.swift_mlx_metallib_link_path.is_file():  # pragma: no cover - filesystem race guard
        raise RuntimeError(
            "Bundled Swift MLX metallib link does not resolve inside the app: "
            f"{layout.swift_mlx_metallib_link_path}"
        )
    timings["copy_swift_mlx_metallib_seconds"] = elapsed_seconds(started_at)
    started_at = time.perf_counter()
    shutil.copy2(resolved_icon_source_path, layout.bundled_icon_path)
    timings["copy_icon_seconds"] = elapsed_seconds(started_at)
    if sparkle_framework is not None:
        started_at = time.perf_counter()
        shutil.copytree(
            sparkle_framework,
            layout.bundled_sparkle_framework_path,
            symlinks=True,
        )
        timings["copy_sparkle_framework_seconds"] = elapsed_seconds(started_at)
        started_at = time.perf_counter()
        _ensure_sparkle_executable_rpath(layout.bundled_app_binary_path)
        timings["configure_sparkle_rpath_seconds"] = elapsed_seconds(started_at)
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
            layout.bundled_control_plane_binary_path,
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
    bundled_resource_bundle_paths: list[Path] = []
    for resource_source_root in dict.fromkeys((executable.parent, swift_worker_executable.parent)):
        for copied_path in _copy_swiftpm_resource_bundles(
            resource_source_root,
            [layout.resources_path],
        ):
            if copied_path not in bundled_resource_bundle_paths:
                bundled_resource_bundle_paths.append(copied_path)
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
    target_metadata["ats_insecure_http_hosts"] = list(
        normalized_insecure_http_hosts
    )
    target_metadata["swift_mlx_metallib_path"] = "mlx.metallib"
    target_metadata["swift_mlx_metallib_version"] = normalized_swift_mlx_metallib_version
    target_metadata["minimum_system_version"] = minimum_system_version
    target_metadata["code_signing"] = {
        "mode": normalized_code_signing_mode,
        "expected_certificate_sha256": normalized_code_signing_certificate_sha256,
        "expected_certificate_sha1": normalized_code_signing_certificate_sha1,
        "expected_authority": normalized_code_signing_authority,
    }
    if sparkle_framework is not None:
        sparkle_public_key_fingerprint = (
            hashlib.sha256(
                base64.b64decode(sparkle_update_configuration["public_ed_key"])
            ).hexdigest()
            if sparkle_update_configuration is not None
            else None
        )
        target_metadata["sparkle_updates"] = {
            "enabled": sparkle_update_configuration is not None,
            "feed_url": (
                sparkle_update_configuration["feed_url"]
                if sparkle_update_configuration is not None
                else None
            ),
            "framework_version": sparkle_framework_version,
            "framework_bytes": _path_size_bytes(
                layout.bundled_sparkle_framework_path
            ),
            "public_key_sha256": sparkle_public_key_fingerprint,
            "requires_user_confirmation": True,
            "automatic_downloads_enabled": False,
        }
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
            insecure_http_hosts=normalized_insecure_http_hosts,
            sparkle_feed_url=(
                sparkle_update_configuration["feed_url"]
                if sparkle_update_configuration is not None
                else None
            ),
            sparkle_public_ed_key=(
                sparkle_update_configuration["public_ed_key"]
                if sparkle_update_configuration is not None
                else None
            ),
            minimum_system_version=minimum_system_version,
        )
    )
    layout.launcher_script_path.write_text(
        render_launcher_script(
            app_name=app_name,
            bundle_repo_root=Path("repo"),
            bundled_app_binary_name=layout.bundled_app_binary_path.name,
            bundled_cli_binary_name=layout.bundled_cli_binary_path.name,
            bundled_control_plane_binary_name=layout.bundled_control_plane_binary_path.name,
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
        layout.bundled_control_plane_binary_path,
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
        "bundled_control_plane_binary_path": str(layout.bundled_control_plane_binary_path),
        "bundled_swift_worker_binary_path": str(layout.bundled_swift_worker_binary_path),
        "bundled_swift_mlx_metallib_path": str(layout.bundled_swift_mlx_metallib_path),
        "swift_mlx_metallib_link_path": str(layout.swift_mlx_metallib_link_path),
        "swift_mlx_metallib_version": normalized_swift_mlx_metallib_version,
        "bundled_python_runtime_path": str(layout.bundled_python_runtime_path),
        "bundled_site_packages_path": str(layout.bundled_site_packages_path),
        "bundled_repo_root_path": str(layout.bundled_repo_root_path),
        "bundled_icon_path": str(layout.bundled_icon_path),
        "bundled_sparkle_framework_path": (
            str(layout.bundled_sparkle_framework_path)
            if sparkle_framework is not None
            else None
        ),
        "sparkle_framework_version": sparkle_framework_version,
        "sparkle_updates_enabled": sparkle_update_configuration is not None,
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
        "ats_insecure_http_hosts": list(normalized_insecure_http_hosts),
        "slimming": slimming,
        "timings": timings,
    }


def _copy_swiftpm_resource_bundles(source_root: Path, target_roots: list[Path]) -> list[Path]:
    copied_paths: list[Path] = []
    try:
        with os.scandir(source_root) as entries:
            bundles: list[tuple[str, str]] = []
            for entry in entries:
                bundle_name = entry.name
                if not bundle_name.endswith(".bundle"):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                bundles.append((bundle_name, entry.path))
            bundles.sort(key=itemgetter(0))
    except OSError:
        return copied_paths

    for bundle_name, source in bundles:
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


def normalize_codesign_certificate_sha1(value: str) -> str:
    normalized = value.strip().replace(":", "").lower()
    if _CERTIFICATE_SHA1_RE.fullmatch(normalized) is None:
        raise ValueError("Code-signing certificate SHA-1 must contain exactly 40 hex digits")
    return normalized


def normalize_codesign_certificate_sha256(value: str) -> str:
    normalized = value.strip().replace(":", "").lower()
    if _CERTIFICATE_SHA256_RE.fullmatch(normalized) is None:
        raise ValueError("Code-signing certificate SHA-256 must contain exactly 64 hex digits")
    return normalized


@dataclass(frozen=True)
class MacOSCodeSigningTarget:
    path: Path
    role: str
    preserve_entitlements: bool = False
    disable_library_validation: bool = False


def _is_packaged_dynamic_code_host(app: Path, path: Path) -> bool:
    relative_path = path.relative_to(app)
    if relative_path in _DYNAMIC_CODE_HOST_RELATIVE_PATHS:
        return True
    return (
        relative_path.parent == Path("Contents/Resources/python-runtime/bin")
        and _VERSIONED_PYTHON_EXECUTABLE_RE.fullmatch(relative_path.name) is not None
    )


def macos_code_signing_plan(app_path: str | Path) -> list[MacOSCodeSigningTarget]:
    """Return Sparkle's required inside-out order followed by other leaf code."""

    app = Path(app_path).expanduser().resolve()
    sparkle_framework = app / "Contents/Frameworks/Sparkle.framework"
    plan: list[MacOSCodeSigningTarget] = []
    if sparkle_framework.exists():
        fixed_targets = [
            MacOSCodeSigningTarget(
                sparkle_framework / "Versions/B/XPCServices/Installer.xpc",
                "sparkle_installer_xpc",
            ),
            MacOSCodeSigningTarget(
                sparkle_framework / "Versions/B/XPCServices/Downloader.xpc",
                "sparkle_downloader_xpc",
                preserve_entitlements=True,
            ),
            MacOSCodeSigningTarget(
                sparkle_framework / "Versions/B/Autoupdate",
                "sparkle_autoupdate",
            ),
            MacOSCodeSigningTarget(
                sparkle_framework / "Versions/B/Updater.app",
                "sparkle_updater_app",
            ),
            MacOSCodeSigningTarget(sparkle_framework, "sparkle_framework"),
        ]
        missing = [target.path for target in fixed_targets if not target.path.exists()]
        if missing:
            raise FileNotFoundError(
                "Sparkle code-signing target is missing: "
                + ", ".join(os.fspath(path) for path in missing)
            )
        plan.extend(fixed_targets)

    other_macho_targets = [
        path
        for path in _iter_nested_macho_signing_targets(app)
        if not sparkle_framework.exists() or sparkle_framework not in path.parents
    ]
    other_macho_targets.sort(
        key=lambda path: (-len(path.relative_to(app).parts), path.as_posix())
    )
    plan.extend(
        MacOSCodeSigningTarget(
            path,
            "nested_macho",
            disable_library_validation=_is_packaged_dynamic_code_host(app, path),
        )
        for path in other_macho_targets
    )
    plan.append(MacOSCodeSigningTarget(app, "outer_app"))
    return plan


def _canonical_codesign_entitlements(codesign: str, target: Path) -> bytes:
    result = subprocess.run(
        [codesign, "--display", "--entitlements", ":-", os.fspath(target)],
        check=True,
        capture_output=True,
    )
    plist_end_marker = b"</plist>"
    for output in (result.stdout, result.stderr, result.stdout + result.stderr):
        xml_start = output.find(b"<?xml")
        if xml_start < 0:
            continue
        plist_end = output.find(plist_end_marker, xml_start)
        if plist_end < 0:
            continue
        xml_end = plist_end + len(plist_end_marker)
        try:
            payload = plistlib.loads(output[xml_start:xml_end])
        except (plistlib.InvalidFileException, ExpatError):
            continue
        if not isinstance(payload, dict):
            raise RuntimeError(f"required entitlements are not a dictionary on {target}")
        return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
    raise RuntimeError(f"required entitlements are missing from {target}")


def _codesign_details(codesign: str, target: Path) -> str:
    details = subprocess.run(
        [codesign, "--display", "--verbose=4", os.fspath(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    return f"{details.stdout}\n{details.stderr}"


def _verify_codesign_identity_evidence(
    codesign: str,
    target: Path,
    *,
    expected_certificate_sha256: str,
    expected_certificate_sha1: str,
    expected_authority: str,
) -> None:
    details = _codesign_details(codesign, target)
    if f"Authority={expected_authority}" not in {
        line.strip() for line in details.splitlines()
    }:
        raise RuntimeError(f"unexpected code-signing authority on {target}")

    requirement = subprocess.run(
        [codesign, "-d", "-r-", os.fspath(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    requirement_text = f"{requirement.stdout}\n{requirement.stderr}".lower()
    if f'certificate root = h"{expected_certificate_sha1}"' not in requirement_text:
        raise RuntimeError(f"designated requirement certificate mismatch on {target}")

    with tempfile.TemporaryDirectory(prefix="melix-codesign-cert-") as directory:
        certificate_prefix = Path(directory) / "certificate"
        subprocess.run(
            [
                codesign,
                "--display",
                "--extract-certificates",
                os.fspath(certificate_prefix),
                os.fspath(target),
            ],
            check=True,
            capture_output=True,
        )
        leaf_certificate = certificate_prefix.with_name(f"{certificate_prefix.name}0")
        certificate = leaf_certificate.read_bytes()
    if hashlib.sha256(certificate).hexdigest() != expected_certificate_sha256:
        raise RuntimeError(f"code-signing certificate SHA-256 mismatch on {target}")
    if hashlib.sha1(certificate).hexdigest() != expected_certificate_sha1:
        raise RuntimeError(f"code-signing certificate SHA-1 mismatch on {target}")


def sign_macos_app_bundle(
    app_path: str | Path,
    *,
    identity: str,
    keychain_path: str | Path | None = None,
    expected_certificate_sha256: str | None = None,
    expected_certificate_sha1: str | None = None,
    expected_authority: str | None = None,
) -> bool:
    app = Path(app_path).expanduser().resolve()
    codesign = shutil.which("codesign")
    if codesign is None:
        return False

    normalized_identity = identity.strip()
    if not normalized_identity:
        raise ValueError("Code-signing identity must not be empty")
    normalized_keychain = (
        Path(keychain_path).expanduser().resolve()
        if keychain_path is not None
        else None
    )
    identity_expectations = (
        expected_certificate_sha256,
        expected_certificate_sha1,
        expected_authority,
    )
    if any(value is not None for value in identity_expectations) and not all(
        value is not None for value in identity_expectations
    ):
        raise ValueError(
            "Expected code-signing certificate SHA-256, SHA-1, and authority must be provided together"
        )
    normalized_expected_sha256 = (
        normalize_codesign_certificate_sha256(expected_certificate_sha256)
        if expected_certificate_sha256 is not None
        else None
    )
    normalized_expected_sha1 = (
        normalize_codesign_certificate_sha1(expected_certificate_sha1)
        if expected_certificate_sha1 is not None
        else None
    )
    normalized_expected_authority = (
        expected_authority.strip() if expected_authority is not None else None
    )
    if expected_authority is not None and not normalized_expected_authority:
        raise ValueError("Expected code-signing authority must not be empty")
    if (
        normalized_expected_sha1 is not None
        and normalize_codesign_certificate_sha1(normalized_identity)
        != normalized_expected_sha1
    ):
        raise ValueError(
            "Code-signing identity must match the expected certificate SHA-1"
        )

    def sign_command(
        target: MacOSCodeSigningTarget,
        *,
        library_validation_entitlements_path: Path,
    ) -> list[str]:
        command = [
            codesign,
            "--force",
            "--options",
            "runtime",
            "--sign",
            normalized_identity,
            "--timestamp=none",
        ]
        if normalized_keychain is not None:
            command.extend(["--keychain", os.fspath(normalized_keychain)])
        if target.preserve_entitlements:
            command.append("--preserve-metadata=entitlements")
        elif target.disable_library_validation:
            command.extend(
                ["--entitlements", os.fspath(library_validation_entitlements_path)]
            )
        command.append(os.fspath(target.path))
        return command

    try:
        plan = macos_code_signing_plan(app)
        if any(
            target.preserve_entitlements and target.disable_library_validation
            for target in plan
        ):
            raise RuntimeError(
                "A code-signing target cannot preserve entitlements and receive the "
                "library-validation exception"
            )
        expected_library_validation_entitlements = plistlib.dumps(
            _DISABLE_LIBRARY_VALIDATION_ENTITLEMENTS,
            fmt=plistlib.FMT_XML,
            sort_keys=True,
        )
        entitlement_snapshots = {}
        for target in plan:
            if target.preserve_entitlements:
                entitlement_snapshots[target.path] = _canonical_codesign_entitlements(
                    codesign, target.path
                )
            elif target.disable_library_validation:
                entitlement_snapshots[target.path] = expected_library_validation_entitlements

        with tempfile.TemporaryDirectory(prefix="melix-codesign-entitlements-") as directory:
            library_validation_entitlements_path = (
                Path(directory) / "disable-library-validation.plist"
            )
            library_validation_entitlements_path.write_bytes(
                expected_library_validation_entitlements
            )
            for target in plan:
                subprocess.run(
                    sign_command(
                        target,
                        library_validation_entitlements_path=(
                            library_validation_entitlements_path
                        ),
                    ),
                    check=True,
                )
        for target in plan:
            subprocess.run(
                [
                    codesign,
                    "--verify",
                    "--strict",
                    "--verbose=4",
                    os.fspath(target.path),
                ],
                check=True,
            )
            details = _codesign_details(codesign, target.path)
            if "runtime" not in details:
                raise RuntimeError(f"hardened runtime is missing on {target.path}")
            if target.path in entitlement_snapshots:
                if (
                    _canonical_codesign_entitlements(codesign, target.path)
                    != entitlement_snapshots[target.path]
                ):
                    raise RuntimeError(f"entitlements changed while signing {target.path}")
            if normalized_expected_sha1 is not None:
                assert normalized_expected_sha256 is not None
                assert normalized_expected_authority is not None
                _verify_codesign_identity_evidence(
                    codesign,
                    target.path,
                    expected_certificate_sha256=normalized_expected_sha256,
                    expected_certificate_sha1=normalized_expected_sha1,
                    expected_authority=normalized_expected_authority,
                )
    except (OSError, RuntimeError, subprocess.CalledProcessError, plistlib.InvalidFileException):
        return False
    return True


def adhoc_sign_macos_app_bundle(app_path: str | Path) -> bool:
    return sign_macos_app_bundle(app_path, identity="-")


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
