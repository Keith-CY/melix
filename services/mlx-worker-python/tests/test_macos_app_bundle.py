from __future__ import annotations

import base64
import hashlib
import json
import os
import plistlib
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import worker.productization.macos_app_bundle as macos_app_bundle_module
import worker.productization.packaged_socket_root as packaged_socket_root_module
from worker.productization.mcp_credential_environment import (
    CLI_PARENT_ENVIRONMENT_KEYS,
    COMMON_CHILD_ENVIRONMENT_KEYS,
    CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS,
    LAUNCHER_INTERNAL_ENVIRONMENT_KEYS,
    MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS,
    PRIVATE_SERVICE_ENVIRONMENT_KEYS,
    PYTHON_WORKER_OWNED_ENVIRONMENT_KEYS,
    STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS,
    SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS,
)

from worker.productization.macos_app_bundle import (
    _copy_swiftpm_resource_bundles,
    _reject_external_python_framework_runtime,
    _copy_packaged_script,
    _ensure_sparkle_executable_rpath,
    _is_macho_file,
    _iter_nested_macho_signing_targets,
    _iter_python_native_binary_candidates,
    _path_size_bytes,
    _prune_python_package_baggage,
    _prune_python_runtime_baggage,
    _read_sparkle_framework_version,
    _strip_packaged_binaries,
    adhoc_sign_macos_app_bundle,
    archive_macos_app_bundle,
    build_macos_app_bundle_layout,
    macos_code_signing_plan,
    normalize_codesign_certificate_sha1,
    render_info_plist,
    render_launcher_script,
    render_native_launcher_source,
    render_portable_environment_script,
    resolve_python_runtime_root,
    resolve_site_packages_root,
    sign_macos_app_bundle,
    write_unsigned_macos_app_bundle,
)
from worker.productization.packaged_socket_root import (
    DARWIN_UNIX_SOCKET_PATH_MAX_BYTES,
    PackagedSocketRootError,
    create_packaged_socket_root,
    packaged_socket_paths,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_build_macos_app_bundle_layout_uses_standard_app_structure(tmp_path: Path) -> None:
    layout = build_macos_app_bundle_layout(tmp_path / "Melix.app")

    assert layout.contents_path == layout.app_path / "Contents"
    assert layout.macos_path == layout.contents_path / "MacOS"
    assert layout.frameworks_path == layout.contents_path / "Frameworks"
    assert layout.resources_path == layout.contents_path / "Resources"
    assert layout.launcher_path == layout.macos_path / "Melix"
    assert layout.launcher_script_path == layout.resources_path / "Melix.sh"
    assert layout.bundled_app_binary_path == layout.macos_path / "melix-menubar"
    assert layout.bundled_cli_binary_path == layout.resources_path / "melix"
    assert layout.bundled_control_plane_binary_path == layout.resources_path / "melix-control-plane"
    assert layout.bundled_swift_worker_binary_path == layout.resources_path / "melix-text-worker-swift"
    assert (
        layout.bundled_computer_broker_binary_path
        == layout.resources_path
        / "MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker"
    )
    assert (
        layout.bundled_computer_broker_plist_path
        == layout.resources_path / "MelixComputerUseBroker.app/Contents/Info.plist"
    )
    assert layout.bundled_swift_mlx_metallib_path == layout.resources_path / "swift-mlx/mlx.metallib"
    assert layout.swift_mlx_metallib_link_path == layout.resources_path / "mlx.metallib"
    assert layout.bundled_icon_path == layout.resources_path / "MelixAppIcon.icns"
    assert layout.bundled_sparkle_framework_path == layout.frameworks_path / "Sparkle.framework"


def test_macos_app_bundle_places_visible_ui_binary_inside_contents_macos(
    tmp_path: Path,
) -> None:
    layout = build_macos_app_bundle_layout(tmp_path / "Melix.app")

    assert layout.bundled_app_binary_path == layout.macos_path / "melix-menubar"
    assert layout.bundled_app_binary_path != layout.launcher_path


def test_render_info_plist_sets_bundle_icon_and_dock_visible_defaults() -> None:
    payload = plistlib.loads(
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.1.0",
            icon_file="MelixAppIcon.icns",
        )
    )

    assert payload["CFBundleExecutable"] == "Melix"
    assert payload["CFBundleIconFile"] == "MelixAppIcon.icns"
    assert payload["CFBundleIdentifier"] == "io.melix.menubar.preview"
    assert payload["NSAppTransportSecurity"] == {
        "NSAllowsLocalNetworking": True,
    }
    assert payload["NSLocalNetworkUsageDescription"] == (
        "Connect to remote AI providers that you configure on your local network or tailnet."
    )
    assert "LSUIElement" not in payload


def test_minimum_system_version_is_derived_from_single_package_platform(
    tmp_path: Path,
) -> None:
    package = tmp_path / "apps/macos-menubar/Package.swift"
    package.parent.mkdir(parents=True)
    package.write_text("let package = Package(platforms: [.macOS(.v15)])\n", encoding="utf-8")
    assert macos_app_bundle_module.resolve_macos_minimum_system_version(tmp_path) == "15.0"

    package.write_text("let package = Package(platforms: [])\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        macos_app_bundle_module.resolve_macos_minimum_system_version(tmp_path)


def test_bundle_writer_rejects_noncanonical_minimum_system_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MAJOR.0"):
        write_unsigned_macos_app_bundle(
            repo_root=tmp_path,
            executable_path=tmp_path / "app",
            cli_executable_path=tmp_path / "cli",
            control_plane_executable_path=tmp_path / "control",
            swift_text_worker_executable_path=tmp_path / "worker",
            computer_broker_executable_path=tmp_path / "broker",
            swift_mlx_metallib_path=tmp_path / "mlx.metallib",
            swift_mlx_metallib_version="0.29.1",
            python_runtime_root=tmp_path / "python",
            python_site_packages_path=tmp_path / "site-packages",
            output_path=tmp_path / "Melix.app",
            minimum_system_version="15",
        )


def test_render_info_plist_adds_only_explicit_insecure_http_host_exceptions() -> None:
    payload = plistlib.loads(
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.1.0",
            icon_file="MelixAppIcon.icns",
            insecure_http_hosts=(
                "192.0.2.10",
                "Provider.Tailnet.TS.NET.",
                "192.0.2.10",
            ),
        )
    )

    assert payload["NSAppTransportSecurity"] == {
        "NSAllowsLocalNetworking": True,
        "NSExceptionDomains": {
            "192.0.2.10": {
                "NSExceptionAllowsInsecureHTTPLoads": True,
            },
            "provider.tailnet.ts.net": {
                "NSExceptionAllowsInsecureHTTPLoads": True,
            },
        },
    }


def test_render_info_plist_enables_only_signed_user_confirmed_updates() -> None:
    public_key = base64.b64encode(bytes(range(32))).decode("ascii")
    payload = plistlib.loads(
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.2.0",
            icon_file="MelixAppIcon.icns",
            sparkle_feed_url=(
                "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
            ),
            sparkle_public_ed_key=public_key,
        )
    )

    assert payload["SUFeedURL"] == (
        "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
    )
    assert payload["SUPublicEDKey"] == public_key
    assert payload["SUEnableAutomaticChecks"] is True
    assert payload["SUAllowsAutomaticUpdates"] is False
    assert payload["SUScheduledCheckInterval"] == 86_400
    assert payload["SUVerifyUpdateBeforeExtraction"] is True
    assert payload["SURequireSignedFeed"] is True


@pytest.mark.parametrize(
    ("feed_url", "public_key", "message"),
    [
        (
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
            None,
            "must be provided together",
        ),
        (
            "https://example.com/appcast.xml",
            base64.b64encode(bytes(range(32))).decode("ascii"),
            "stable signed Melix",
        ),
        (
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
            "not-base64",
            "valid base64",
        ),
        (
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
            base64.b64encode(b"short").decode("ascii"),
            "exactly 32 bytes",
        ),
    ],
)
def test_render_info_plist_rejects_incomplete_or_untrusted_update_configuration(
    feed_url: str | None,
    public_key: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.2.0",
            icon_file="MelixAppIcon.icns",
            sparkle_feed_url=feed_url,
            sparkle_public_ed_key=public_key,
        )


def test_write_unsigned_bundle_separates_preview_and_signed_release_identity(
    tmp_path: Path,
) -> None:
    common = {
        "repo_root": tmp_path / "repo",
        "executable_path": tmp_path / "melix-menubar",
        "cli_executable_path": tmp_path / "melix",
        "control_plane_executable_path": tmp_path / "melix-control-plane",
        "swift_text_worker_executable_path": tmp_path / "melix-text-worker-swift",
        "computer_broker_executable_path": tmp_path / "melix-computer-broker",
        "swift_mlx_metallib_path": tmp_path / "mlx.metallib",
        "swift_mlx_metallib_version": "0.31.1",
        "python_runtime_root": tmp_path / "python-runtime",
        "python_site_packages_path": tmp_path / "site-packages",
        "output_path": tmp_path / "Melix.app",
    }
    public_key = base64.b64encode(bytes(range(32))).decode("ascii")

    with pytest.raises(ValueError, match="stable Melix release bundle ID"):
        write_unsigned_macos_app_bundle(
            **common,
            sparkle_feed_url=(
                "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
            ),
            sparkle_public_ed_key=public_key,
        )

    with pytest.raises(ValueError, match="must not be used without signed updates"):
        write_unsigned_macos_app_bundle(
            **common,
            bundle_id="io.melix.menubar",
            packaging_target_id="macos_app_bundle_github_release",
        )

    with pytest.raises(ValueError, match="stable self-signed code-signing metadata"):
        write_unsigned_macos_app_bundle(
            **common,
            bundle_id="io.melix.menubar",
            packaging_target_id="macos_app_bundle_github_release",
            sparkle_feed_url=(
                "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
            ),
            sparkle_public_ed_key=public_key,
        )

    with pytest.raises(ValueError, match="Preview bundles require ad-hoc"):
        write_unsigned_macos_app_bundle(
            **common,
            code_signing_mode="stable_self_signed",
        )

    with pytest.raises(ValueError, match="must not declare a release"):
        write_unsigned_macos_app_bundle(
            **common,
            code_signing_certificate_sha1="0" * 40,
            code_signing_authority="Melix GitHub Release Signing",
        )


@pytest.mark.parametrize(
    "host",
    [
        "",
        "http://192.0.2.10",
        "192.0.2.10:50650",
        "*.tailnet.ts.net",
        "2001:db8::1",
        "-invalid.example",
        "\ud800.example",
    ],
)
def test_render_info_plist_rejects_invalid_insecure_http_hosts(host: str) -> None:
    with pytest.raises(ValueError, match="ATS insecure HTTP host"):
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.1.0",
            icon_file="MelixAppIcon.icns",
            insecure_http_hosts=(host,),
        )


def test_render_portable_environment_script_uses_home_relative_paths() -> None:
    script = render_portable_environment_script(
        product_version="0.8.11",
        update_channel_path="/tmp/stable.json",
        logical_product_identity="io.melix",
        packaging_target_id="macos_app_bundle_preview",
        packaging_kind="app_bundle",
        http_bind_host="0.0.0.0",
        http_connect_host="127.0.0.1",
        http_port=12436,
    )

    assert 'export MELIX_LOGICAL_PRODUCT_ID="io.melix"' in script
    assert 'export MELIX_PACKAGING_TARGET_ID="macos_app_bundle_preview"' in script
    assert 'export MELIX_PACKAGING_KIND="app_bundle"' in script
    assert 'export MELIX_PRODUCT_VERSION="0.8.11"' in script
    assert "MELIX_APP_SUPPORT_DIR" not in script
    assert 'export MELIX_HOME="${MELIX_HOME:-$HOME/.melix}"' in script
    assert 'export MELIX_RUNTIME_DIR="${MELIX_RUNTIME_DIR:-$MELIX_HOME/run}"' in script
    assert 'export MELIX_MANAGED_MODEL_ROOT="${MELIX_MANAGED_MODEL_ROOT:-$MELIX_HOME/models/default-managed}"' in script
    assert (
        'export MELIX_AUDIO_RUNTIME_PACK_ROOT="${MELIX_AUDIO_RUNTIME_PACK_ROOT:-$MELIX_HOME/runtime-packs/audio}"'
        in script
    )
    assert 'export MELIX_MODEL_OPS_JOBS_ROOT="${MELIX_MODEL_OPS_JOBS_ROOT:-$MELIX_HOME/jobs/model-ops}"' in script
    assert 'export MELIX_EVALUATION_JOBS_ROOT="${MELIX_EVALUATION_JOBS_ROOT:-$MELIX_HOME/jobs/evaluation}"' in script
    assert (
        'export MELIX_GATEWAY_CONFIG_STORE_PATH="${MELIX_GATEWAY_CONFIG_STORE_PATH:-$MELIX_HOME/config/gateway-config.json}"'
        in script
    )
    assert (
        'export MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH="${MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH:-$MELIX_HOME/config/gateway-serving-defaults.json}"'
        in script
    )
    assert (
        'export MELIX_IMAGE_DEFAULTS_STORE_PATH="${MELIX_IMAGE_DEFAULTS_STORE_PATH:-$MELIX_HOME/config/image-defaults.json}"'
        in script
    )
    assert (
        'export MELIX_PRODUCT_MANIFEST_PATH="${MELIX_PRODUCT_MANIFEST_PATH:-$MELIX_HOME/install/install-manifest.json}"'
        in script
    )
    assert 'export MELIX_HTTP_HOST="${MELIX_HTTP_HOST:-0.0.0.0}"' in script
    assert 'export MELIX_HTTP_CONNECT_HOST="${MELIX_HTTP_CONNECT_HOST:-127.0.0.1}"' in script
    assert 'export MELIX_HTTP_PORT="${MELIX_HTTP_PORT:-12436}"' in script
    assert 'export MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY="environment"' in script
    assert 'export MELIX_BACKEND_MODE="auto"' in script
    assert 'export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="swift"' in script
    assert 'export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$MELIX_RUNTIME_DIR/python-bytecode-cache}"' in script


def test_render_launcher_script_starts_bundled_workers_and_app(tmp_path: Path) -> None:
    script = render_launcher_script(
        app_name="Melix",
        bundle_repo_root=Path("repo"),
        bundled_app_binary_name="melix-menubar",
        bundled_cli_binary_name="melix",
        bundled_control_plane_binary_name="melix-control-plane",
        bundled_swift_worker_binary_name="melix-text-worker-swift",
        bundled_computer_broker_binary_relative_path="MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker",
        bundled_python_executable_relative_path="python-runtime/bin/python3",
        bundled_site_packages_relative_path="python-site-packages",
        wait_script_relative_path="repo/scripts/wait_for_worker_ready.py",
    )

    assert 'export MELIX_REPO_ROOT="$RESOURCES_DIR/repo"' in script
    assert 'export MELIX_APP_BUNDLE_PATH="$(cd "$CONTENTS_DIR/.." && pwd)"' in script
    assert 'export MELIX_CLI="$RESOURCES_DIR/melix"' in script
    assert 'export MELIX_MENU_BAR_STARTUP_SURFACE="console"' in script
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in script
    assert 'export MELIX_PYTHON_BRIDGE_EXECUTABLE="$RESOURCES_DIR/python-runtime/bin/python3"' in script
    assert "worker.productization.packaged_socket_root" in script
    assert 'MELIX_WORKER_SOCKET_PATH="$MELIX_SOCKET_ROOT/python.sock"' in script
    assert 'MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH="$MELIX_SOCKET_ROOT/swift.sock"' in script
    assert 'export MELIX_CONTROL_PLANE_SOCKET_PATH="$MELIX_SOCKET_ROOT/control.sock"' in script
    assert '"$RESOURCES_DIR/melix-text-worker-swift"' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" -m worker.bootstrap' in script
    assert '--backend-mode "$MELIX_BACKEND_MODE"' in script
    assert "export MELIX_SWIFT_WORKER_PID" not in script
    assert "export MELIX_PYTHON_WORKER_PID" not in script
    assert '"$RESOURCES_DIR/melix-control-plane"' in script
    assert "export MELIX_CONTROL_PLANE_PID" not in script
    assert (
        '"$RESOURCES_DIR/MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker" '
        'serve --socket'
    ) in script
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD=3" in script
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD=4" in script
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64" in script
    assert '--python-worker-socket-path ""' in script
    assert '--swift-text-worker-socket-path ""' in script
    assert 'http://$MELIX_HTTP_CONNECT_HOST:$MELIX_HTTP_PORT/health' in script
    assert "socket.create_connection" in script
    assert "Melix HTTP port %s is already in use" in script
    assert script.index("socket.create_connection") < script.index('"$RESOURCES_DIR/melix-control-plane"')
    assert 'export MELIX_ACTIVE_RUNTIME_PATH=' in script
    assert '-m worker.productization.active_runtime' in script
    assert '--app-process-id "$MELIX_APP_PROCESS_PID"' in script
    assert '--control-plane-process-id "$MELIX_CONTROL_PLANE_PID"' in script
    assert 'MELIX_APP_PROCESS_PID=$!' in script
    assert 'MELIX_APP_PROCESS_PID=$$' not in script
    assert 'while kill -0 "$MELIX_APP_PROCESS_PID"' in script
    assert 'MELIX_WATCHDOG_COMPUTER_BROKER_PID="$MELIX_COMPUTER_BROKER_PID"' in script
    assert 'kill "$MELIX_APP_PROCESS_PID"' in script
    assert script.count('for cleanup_path in "$MELIX_ACTIVE_RUNTIME_PATH"') == 1
    assert script.index('"$CONTENTS_DIR/MacOS/melix-menubar" "$@" &') < script.index(
        'MELIX_APP_PROCESS_PID=$!'
    )
    assert '"$MELIX_RUNTIME_DIR/python-bytecode-cache"' in script
    assert '"$MELIX_MODEL_OPS_JOBS_ROOT"' in script
    assert '"$MELIX_EVALUATION_JOBS_ROOT"' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" "$RESOURCES_DIR/repo/scripts/wait_for_worker_ready.py"' in script
    assert 'MELIX_CONTROL_PLANE_PID="$MELIX_CONTROL_PLANE_PID"' in script
    assert 'MELIX_SWIFT_WORKER_PID="$MELIX_SWIFT_WORKER_PID"' in script
    assert 'MELIX_PYTHON_WORKER_PID="$MELIX_PYTHON_WORKER_PID"' in script
    assert (
        'MELIX_MCP_CREDENTIAL_ENV_KEYS="$(join_frozen_mcp_credential_keys)" '
        '"$CONTENTS_DIR/MacOS/melix-menubar" "$@" &'
    ) in script
    assert '/usr/bin/env -i "${PYTHON_WORKER_CHILD_ENVIRONMENT[@]}"' in script
    assert "backend-mode deterministic" not in script


def test_packaged_socket_root_is_private_bounded_and_unique() -> None:
    first = create_packaged_socket_root("boundary")
    second = create_packaged_socket_root("boundary")
    try:
        assert first != second
        for root in (first, second):
            info = os.lstat(root)
            assert info.st_uid == os.geteuid()
            assert info.st_mode & 0o777 == 0o700
            assert all(
                len(os.fsencode(path)) <= DARWIN_UNIX_SOCKET_PATH_MAX_BYTES
                for path in packaged_socket_paths(root)
            )
    finally:
        first.rmdir()
        second.rmdir()


def test_packaged_socket_root_creation_failure_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_creation(*_args: object, **_kwargs: object) -> str:
        raise OSError("fixture create failure")

    monkeypatch.setattr(packaged_socket_root_module.tempfile, "mkdtemp", fail_creation)

    with pytest.raises(PackagedSocketRootError, match="fixture create failure"):
        create_packaged_socket_root("failure", parent=tmp_path)


def test_packaged_socket_root_removes_unsafe_factory_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe = tmp_path / "melix-unsafe"

    def create_unsafe(*, prefix: str, dir: str) -> str:
        assert prefix.startswith(f"melix-{os.geteuid()}-unsafe.")
        assert Path(dir) == tmp_path
        unsafe.mkdir(mode=0o700)
        unsafe.chmod(0o755)
        return os.fspath(unsafe)

    monkeypatch.setattr(packaged_socket_root_module.tempfile, "mkdtemp", create_unsafe)

    with pytest.raises(PackagedSocketRootError, match="mode 0700"):
        create_packaged_socket_root("unsafe", parent=tmp_path)
    assert not unsafe.exists()


def test_packaged_socket_root_validation_rejects_untrusted_shapes(tmp_path: Path) -> None:
    with pytest.raises(PackagedSocketRootError, match="direct child"):
        packaged_socket_root_module.validate_packaged_socket_root(
            "relative/socket-root",
            parent=tmp_path,
        )

    missing = tmp_path / "missing"
    with pytest.raises(PackagedSocketRootError, match="unable to inspect"):
        packaged_socket_root_module.validate_packaged_socket_root(
            missing,
            parent=tmp_path,
        )

    regular_file = tmp_path / "regular"
    regular_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(PackagedSocketRootError, match="not a real directory"):
        packaged_socket_root_module.validate_packaged_socket_root(
            regular_file,
            parent=tmp_path,
        )

    owned_directory = tmp_path / "owned"
    owned_directory.mkdir(mode=0o700)
    with pytest.raises(PackagedSocketRootError, match="not owned"):
        packaged_socket_root_module.validate_packaged_socket_root(
            owned_directory,
            effective_uid=os.geteuid() + 1,
            parent=tmp_path,
        )


def test_packaged_socket_root_validation_rejects_overlong_socket_paths(
    tmp_path: Path,
) -> None:
    long_parent = tmp_path / ("p" * 80)
    long_parent.mkdir()
    socket_root = long_parent / "socket-root"
    socket_root.mkdir(mode=0o700)

    with pytest.raises(PackagedSocketRootError, match="103-byte"):
        packaged_socket_root_module.validate_packaged_socket_root(
            socket_root,
            parent=long_parent,
        )


def test_packaged_socket_root_rejects_invalid_run_token() -> None:
    with pytest.raises(PackagedSocketRootError, match="run token"):
        create_packaged_socket_root("not valid")


def test_packaged_socket_root_reports_unsafe_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe = tmp_path / "melix-unsafe-cleanup"

    def create_unsafe(*, prefix: str, dir: str) -> str:
        assert prefix.startswith(f"melix-{os.geteuid()}-unsafe.")
        assert Path(dir) == tmp_path
        unsafe.mkdir(mode=0o755)
        return os.fspath(unsafe)

    def fail_cleanup(path: str | os.PathLike[str]) -> None:
        assert Path(path) == unsafe
        raise OSError("fixture cleanup failure")

    monkeypatch.setattr(packaged_socket_root_module.tempfile, "mkdtemp", create_unsafe)
    monkeypatch.setattr(packaged_socket_root_module.os, "rmdir", fail_cleanup)

    with pytest.raises(PackagedSocketRootError, match="could not be removed"):
        create_packaged_socket_root("unsafe", parent=tmp_path)


def test_packaged_socket_root_main_reports_success_and_typed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    socket_root = tmp_path / "socket-root"
    socket_root.mkdir(mode=0o700)
    monkeypatch.setattr(
        packaged_socket_root_module,
        "create_packaged_socket_root",
        lambda run_token: socket_root,
    )

    assert packaged_socket_root_module.main(["--run-token", "fixture"]) == 0
    assert capsys.readouterr().out.strip() == os.fspath(socket_root)

    def fail_creation(_run_token: str) -> Path:
        raise PackagedSocketRootError("fixture typed failure")

    monkeypatch.setattr(
        packaged_socket_root_module,
        "create_packaged_socket_root",
        fail_creation,
    )
    assert packaged_socket_root_module.main(["--run-token", "fixture"]) == 1
    assert "fixture typed failure" in capsys.readouterr().err


def test_render_launcher_script_fails_closed_and_removes_broker_trust_material() -> None:
    script = render_launcher_script(
        app_name="Melix",
        bundle_repo_root=Path("repo"),
        bundled_app_binary_name="melix-menubar",
        bundled_cli_binary_name="melix",
        bundled_control_plane_binary_name="melix-control-plane",
        bundled_swift_worker_binary_name="melix-text-worker-swift",
        bundled_computer_broker_binary_relative_path="MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker",
        bundled_python_executable_relative_path="python-runtime/bin/python3",
        bundled_site_packages_relative_path="python-site-packages",
        wait_script_relative_path="repo/scripts/wait_for_worker_ready.py",
    )

    assert script.index("trap cleanup EXIT INT TERM") < script.index("os.urandom(32)")
    assert script.index('MELIX_CONTROL_PLANE_PID=$!') < script.index(
        'rm -f "$MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE"',
        script.index('MELIX_CONTROL_PLANE_PID=$!'),
    )
    assert script.index('rm -f "$MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE"') < script.index(
        '"$RESOURCES_DIR/MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker"'
    )
    assert "stat.S_ISSOCK(info.st_mode)" in script
    assert "info.st_uid == os.geteuid()" in script
    assert "stat.S_IMODE(info.st_mode) == 0o600" in script
    assert 'terminate_private_process "${MELIX_COMPUTER_BROKER_PID:-}"' in script
    assert '"${MELIX_COMPUTER_BROKER_SOCKET:-}"' in script
    assert '"$MELIX_COMPUTER_BROKER_CAPABILITY_FILE"' in script
    assert '"$MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE"' in script
    assert '"$MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE"' in script
    assert (
        'exec_app_service MELIX_CONTROL_PLANE_SOCKET_PATH="$MELIX_CONTROL_PLANE_SOCKET_PATH" '
        'MELIX_CONTROL_PLANE_PID="$MELIX_CONTROL_PLANE_PID" '
        'MELIX_SWIFT_WORKER_PID="$MELIX_SWIFT_WORKER_PID" '
        'MELIX_PYTHON_WORKER_PID="$MELIX_PYTHON_WORKER_PID" '
        'MELIX_MCP_CREDENTIAL_ENV_KEYS="$(join_frozen_mcp_credential_keys)" '
        '"$CONTENTS_DIR/MacOS/melix-menubar" "$@" &'
    ) in script
    assert 'MELIX_APP_PROCESS_PID=$!' in script
    assert '--app-process-id "$MELIX_APP_PROCESS_PID"' in script
    assert 'wait "$MELIX_APP_PROCESS_PID"' in script
    assert 'MELIX_APP_PROCESS_PID=$$' not in script
    for private_key in (
        "MELIX_WORKER_SOCKET_PATH",
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH",
        "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH",
        "MELIX_COMPUTER_BROKER_SOCKET",
        "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD",
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64",
    ):
        assert f'"-u" "{private_key}"' in script


def test_render_launcher_script_limits_dynamic_mcp_credentials_and_inherited_fds(
    tmp_path: Path,
) -> None:
    script = render_launcher_script(
        app_name="Melix",
        bundle_repo_root=Path("repo"),
        bundled_app_binary_name="melix-menubar",
        bundled_cli_binary_name="melix",
        bundled_control_plane_binary_name="melix-control-plane",
        bundled_swift_worker_binary_name="melix-text-worker-swift",
        bundled_computer_broker_binary_relative_path="MelixComputerUseBroker.app/Contents/MacOS/melix-computer-broker",
        bundled_python_executable_relative_path="python-runtime/bin/python3",
        bundled_site_packages_relative_path="python-site-packages",
        wait_script_relative_path="repo/scripts/wait_for_worker_ready.py",
    )
    script_path = tmp_path / "Melix.sh"
    script_path.write_text(script, encoding="utf-8")

    subprocess.run(["/bin/bash", "-n", str(script_path)], check=True)
    assert (
        "-m worker.productization.mcp_credential_environment --melix-home "
        '"$MELIX_HOME"'
    ) in script
    assert 'INITIAL_MCP_CREDENTIAL_KEYS=("${CURRENT_MCP_CREDENTIAL_KEYS[@]}")' in script
    assert "--validate-frozen-key-snapshot" in script
    assert 'MCP_CREDENTIALS_CAPTURED_BY_PYTHON_WORKER=1' in script
    assert 'unset "$key"' in script
    assert 'join_frozen_mcp_credential_keys' in script
    assert (
        'exec_python_worker_service MELIX_WORKER_SOCKET_PATH="$MELIX_WORKER_SOCKET_PATH" '
        'MELIX_COMPUTER_BROKER_SOCKET="$MELIX_COMPUTER_BROKER_SOCKET"'
    ) in script
    assert (
            'exec_swift_worker_service MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH='
        '"$MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"'
    ) in script
    assert "os.closerange(3, int(os.sysconf(\"SC_OPEN_MAX\")))" in script
    assert "os.closerange(5, int(os.sysconf(\"SC_OPEN_MAX\")))" in script
    assert 'exec_control_plane_service MELIX_WORKER_SOCKET_PATH=' in script
    assert 'run_private_service /usr/bin/curl' in script


def test_app_boundary_declares_every_shared_reserved_environment_key() -> None:
    app_main_source = (
        Path(__file__).resolve().parents[3]
        / "apps/macos-menubar/Sources/AppMain/AppMain.swift"
    ).read_text(encoding="utf-8")

    reserved_block = app_main_source.split("// MCP_RESERVED_ENVIRONMENT_KEYS_BEGIN", 1)[1]
    reserved_block = reserved_block.split("// MCP_RESERVED_ENVIRONMENT_KEYS_END", 1)[0]
    swift_reserved_keys = set(re.findall(r'"([A-Z_][A-Z0-9_]*)"', reserved_block))

    assert swift_reserved_keys == MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS


def test_role_manifests_cover_source_environment_key_inventories() -> None:
    def literals(root: Path, pattern: str) -> set[str]:
        keys: set[str] = set()
        for source_path in root.rglob(pattern):
            keys.update(
                re.findall(
                    r'["\'](MELIX_[A-Z0-9_]+)["\']',
                    source_path.read_text(encoding="utf-8"),
                )
            )
        return keys

    common = set(COMMON_CHILD_ENVIRONMENT_KEYS)
    private = set(PRIVATE_SERVICE_ENVIRONMENT_KEYS)
    launcher_internal = set(LAUNCHER_INTERNAL_ENVIRONMENT_KEYS)
    control_plane_literals = literals(
        REPO_ROOT / "services/control-plane-swift/Sources",
        "*.swift",
    )
    swift_worker_literals = literals(
        REPO_ROOT / "services/mlx-text-worker-swift/Sources",
        "*.swift",
    )
    python_worker_literals = literals(
        REPO_ROOT / "services/mlx-worker-python/worker",
        "*.py",
    )
    cli_literals = literals(REPO_ROOT / "Sources/MelixCLICore", "*.swift")

    assert control_plane_literals <= (
        common
        | set(CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS)
        | private
        | launcher_internal
        | set(STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS)
    )
    assert set(CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS) <= control_plane_literals
    assert swift_worker_literals <= (
        common
        | set(SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS)
        | private
        | launcher_internal
    )
    assert set(SWIFT_WORKER_PARENT_ENVIRONMENT_KEYS) <= swift_worker_literals
    assert python_worker_literals <= MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS
    assert set(PYTHON_WORKER_OWNED_ENVIRONMENT_KEYS) <= python_worker_literals
    assert set(STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS).isdisjoint(
        CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS
    )
    denied_cli_private_keys = {
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH",
        "MELIX_WORKER_SOCKET_PATH",
    }
    assert cli_literals - denied_cli_private_keys <= (
        common
        | set(CLI_PARENT_ENVIRONMENT_KEYS)
        | {"MELIX_CONTROL_PLANE_SOCKET_PATH"}
    )
    assert set(CLI_PARENT_ENVIRONMENT_KEYS) <= cli_literals
    assert denied_cli_private_keys.isdisjoint(CLI_PARENT_ENVIRONMENT_KEYS)


@pytest.mark.parametrize(
    "rotation_mode",
    (
        "initially-authorized",
        "new-key",
        "cross-kind-reference",
        "cleanup-residue",
        "no-credentials",
    ),
)
def test_rendered_launcher_enforces_runtime_environment_and_fd_boundaries(
    tmp_path: Path,
    rotation_mode: str,
    request: pytest.FixtureRequest,
) -> None:
    contents_dir = tmp_path / "Melix.app/Contents"
    resources_dir = contents_dir / "Resources"
    resources_dir.mkdir(parents=True)
    repo_services = resources_dir / "repo/services"
    repo_services.mkdir(parents=True)
    repo_services.joinpath("mlx-worker-python").symlink_to(
        Path(__file__).resolve().parents[1],
        target_is_directory=True,
    )
    record_dir = tmp_path / "records"
    record_dir.mkdir()
    melix_home = tmp_path / "home"
    config_path = melix_home / "config/mcp-tools.json"
    config_path.parent.mkdir(parents=True)
    initial_references = {"TOKEN": "INITIAL_SECRET"}
    if rotation_mode in ("initially-authorized", "cleanup-residue"):
        initial_references["ROTATED_TOKEN"] = "ROTATED_SECRET"
    rotation_references = {"Authorization": "ROTATED_SECRET"}
    initial_transport = {
        "kind": "stdio",
        "command": "/usr/bin/true",
        "environment_references": initial_references,
    }
    if rotation_mode == "cross-kind-reference":
        initial_transport["header_environment_references"] = {
            "Authorization": "CROSS_KIND_SECRET"
        }
    initial_sources = [] if rotation_mode == "no-credentials" else [
        {
            "source_id": "initial-source",
            "transport": initial_transport,
        }
    ]
    config_path.write_text(
        json.dumps(
            {
                "sources": initial_sources
            }
        ),
        encoding="utf-8",
    )
    python_runtime = resources_dir / "python-runtime/bin/python3"
    python_runtime.parent.mkdir(parents=True)
    python_runtime.write_text(
        f"""#!{sys.executable}
import json, os, socket, stat, sys, time
REAL_PYTHON = {sys.executable!r}
RECORD_KEYS = ("INITIAL_SECRET", "ROTATED_SECRET", "CROSS_KIND_SECRET", "UNREFERENCED_SECRET", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "MELIX_MCP_CREDENTIAL_ENV_KEYS", "MELIX_WORKER_SOCKET_PATH", "MELIX_COMPUTER_BROKER_SOCKET", "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE", "MELIX_COMPUTER_BROKER_CAPABILITY_FILE", "MELIX_COMPUTER_BROKER_DIR", "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE", "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE", "MELIX_GATEWAY_AUTH_MODE", "MELIX_GATEWAY_API_KEYS_JSON", "MELIX_GATEWAY_BEARER_TOKEN", "MELIX_MCP_HIGH_RISK_ALLOWLIST", "MELIX_API_KEY", "MELIX_HF_TOKEN", "MELIX_HUGGINGFACE_TOKEN")
def fds():
    result = []
    for fd in range(3, 64):
        try: os.fstat(fd)
        except OSError: continue
        result.append(fd)
    return result
def record(role, socket_path=None):
    root = os.path.dirname(os.environ["MELIX_WORKER_SOCKET_PATH"])
    root_info = os.lstat(root)
    payload = {{"environment": {{key: os.environ.get(key) for key in RECORD_KEYS}}, "fds": fds(), "socket_root": {{"path": root, "uid": root_info.st_uid, "mode": stat.S_IMODE(root_info.st_mode)}}}}
    with open(os.path.join({str(record_dir)!r}, role + ".json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
args = sys.argv[1:]
if args[:2] == ["-m", "worker.bootstrap"]:
    record("python-worker")
    config_path = os.environ.get("MELIX_MCP_CONFIG_PATH") or os.path.join(os.environ["MELIX_HOME"], "config/mcp-tools.json")
    with open(config_path, encoding="utf-8") as handle: config = json.load(handle)
    if {rotation_mode != "no-credentials"!r}:
        config["sources"].append({{"source_id": "rotated-source", "transport": {{"kind": "streamable_http", "url": "https://mcp.example.test/rpc", "header_environment_references": {rotation_references!r}}}}})
        replacement = config_path + ".next"
        with open(replacement, "w", encoding="utf-8") as handle: json.dump(config, handle)
        os.replace(replacement, config_path)
    socket_path = args[args.index("--socket-path") + 1]
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(socket_path)
    while True: time.sleep(1)
if args[:2] == ["-m", "worker.productization.active_runtime"]:
    output_path = args[args.index("--output-path") + 1]
    with open(output_path, "w", encoding="utf-8") as handle: handle.write("{{}}")
    with open(os.path.join({str(record_dir)!r}, "active-runtime.json"), "w", encoding="utf-8") as handle:
        json.dump({{"args": args}}, handle, sort_keys=True)
    raise SystemExit(0)
if args and args[0].endswith("wait.py"):
    socket_path = args[args.index("--socket-path") + 1]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if os.path.exists(socket_path): raise SystemExit(0)
        time.sleep(0.02)
    raise SystemExit(1)
os.execve(REAL_PYTHON, [REAL_PYTHON, *args], os.environ)
""",
        encoding="utf-8",
    )
    python_runtime.chmod(0o755)

    recorder_prelude = f"""#!{sys.executable}
import json, os, stat
RECORD_DIR = {str(record_dir)!r}
def record(role, socket_path=None):
    fds = []
    for fd in range(3, 64):
        try: os.fstat(fd)
        except OSError: continue
        fds.append(fd)
    keys = ("INITIAL_SECRET", "ROTATED_SECRET", "UNREFERENCED_SECRET", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "MELIX_WORKER_SOCKET_PATH", "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", "MELIX_CONTROL_PLANE_SOCKET_PATH", "MELIX_COMPUTER_BROKER_SOCKET", "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE", "MELIX_COMPUTER_BROKER_CAPABILITY_FILE", "MELIX_COMPUTER_BROKER_DIR", "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE", "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE", "MELIX_GATEWAY_AUTH_MODE", "MELIX_GATEWAY_API_KEYS_JSON", "MELIX_GATEWAY_BEARER_TOKEN", "MELIX_MCP_HIGH_RISK_ALLOWLIST", "MELIX_API_KEY", "MELIX_HF_TOKEN", "MELIX_HUGGINGFACE_TOKEN", "MELIX_MCP_CONFIG_PATH", "MELIX_HTTP_HOST", "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE", "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT", "MELIX_MENU_BAR_TERMINATION_MODE", "MELIX_BATCH_RUN_ID", "MELIX_CONTROL_PLANE_PID", "MELIX_SWIFT_WORKER_PID", "MELIX_PYTHON_WORKER_PID")
    if socket_path is None:
        socket_path = next(os.environ[key] for key in ("MELIX_WORKER_SOCKET_PATH", "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", "MELIX_CONTROL_PLANE_SOCKET_PATH", "MELIX_COMPUTER_BROKER_SOCKET") if os.environ.get(key))
    root = os.path.dirname(socket_path)
    if socket_path.endswith("/computer-broker/broker.sock"):
        root = os.path.dirname(root)
    root_info = os.lstat(root)
    with open(os.path.join(RECORD_DIR, role + ".json"), "w", encoding="utf-8") as handle:
        json.dump({{"environment": {{key: os.environ.get(key) for key in keys}}, "fds": fds, "effective_socket_path": socket_path, "pid": os.getpid(), "socket_root": {{"path": root, "uid": root_info.st_uid, "mode": stat.S_IMODE(root_info.st_mode)}}}}, handle, sort_keys=True)
"""
    swift_worker = resources_dir / "melix-text-worker-swift"
    swift_worker.write_text(
        recorder_prelude
        + """import socket, time
record("swift-worker")
listener = socket.socket(socket.AF_UNIX)
listener.bind(os.environ["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"])
while True: time.sleep(1)
""",
        encoding="utf-8",
    )
    control_plane = resources_dir / "melix-control-plane"
    control_plane.write_text(
        recorder_prelude
        + """from http.server import BaseHTTPRequestHandler, HTTPServer
record("control-plane")
with open(os.environ["MELIX_CONTROL_PLANE_SOCKET_PATH"] + ".lock", "w", encoding="utf-8") as handle:
    handle.write("fixture control-plane lease\\n")
os.write(4, b"p" * 32)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, format, *args): pass
HTTPServer((os.environ["MELIX_HTTP_CONNECT_HOST"], int(os.environ["MELIX_HTTP_PORT"])), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    broker = resources_dir / "melix-computer-broker"
    broker.write_text(
        recorder_prelude
        + """import socket, sys, time
socket_path = sys.argv[sys.argv.index("--socket") + 1]
record("broker", socket_path)
with open(socket_path + ".lock", "w", encoding="utf-8") as handle:
    handle.write("fixture broker lease\\n")
listener = socket.socket(socket.AF_UNIX)
listener.bind(socket_path)
os.chmod(socket_path, 0o600)
while True: time.sleep(1)
""",
        encoding="utf-8",
    )
    app = contents_dir / "MacOS/melix-menubar"
    app.parent.mkdir(parents=True)
    app_source = recorder_prelude + 'record("app")\n'
    if rotation_mode == "cleanup-residue":
        app_source += (
            'socket_root = os.path.dirname(os.environ["MELIX_CONTROL_PLANE_SOCKET_PATH"])\n'
            'with open(os.path.join(socket_root, "unexpected-residue"), "w", encoding="utf-8") as handle:\n'
            '    handle.write("fixture residue\\n")\n'
        )
    app.write_text(app_source, encoding="utf-8")
    for executable in (swift_worker, control_plane, broker, app):
        executable.chmod(0o755)

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        http_port = reservation.getsockname()[1]
    (resources_dir / "melix-product-env.sh").write_text(
        render_portable_environment_script(
            product_version="test",
            update_channel_path=tmp_path / "updates",
            logical_product_identity="melix.test",
            packaging_target_id="test",
            packaging_kind="test",
            http_port=http_port,
        ),
        encoding="utf-8",
    )
    launcher_path = resources_dir / "Melix.sh"
    launcher_path.write_text(
        render_launcher_script(
            app_name="Melix",
            bundle_repo_root=Path("repo"),
            bundled_app_binary_name=app.name,
            bundled_cli_binary_name="melix",
            bundled_control_plane_binary_name=control_plane.name,
            bundled_swift_worker_binary_name=swift_worker.name,
            bundled_computer_broker_binary_relative_path=broker.relative_to(
                resources_dir
            ).as_posix(),
            bundled_python_executable_relative_path="python-runtime/bin/python3",
            bundled_site_packages_relative_path="python-site-packages",
            wait_script_relative_path="wait.py",
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)

    runtime_target = tmp_path / ("runtime-" + ("x" * 120))
    runtime_target.mkdir()
    assert len(os.fsencode(runtime_target / "python-worker-boundary-test.sock")) > 103
    sibling_socket_root = None
    if rotation_mode == "initially-authorized":
        sibling_socket_root = create_packaged_socket_root("boundary-test")
        request.addfinalizer(
            lambda: sibling_socket_root.rmdir()
            if sibling_socket_root is not None and sibling_socket_root.exists()
            else None
        )
    inherited_path = tmp_path / "inherited-fd"
    inherited_fd = os.open(inherited_path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.set_inheritable(inherited_fd, True)
    try:
        result = subprocess.run(
            ["/bin/bash", str(launcher_path)],
            env={
                **os.environ,
                "HOME": str(melix_home),
                "MELIX_HOME": str(melix_home),
                "MELIX_MCP_CONFIG_PATH": "~/config/mcp-tools.json",
                "MELIX_RUNTIME_DIR": str(runtime_target),
                "MELIX_HTTP_PORT": str(http_port),
                "MELIX_RUN_TOKEN": "boundary-test",
                "RECORD_DIR": str(record_dir),
                "REAL_PYTHON": sys.executable,
                "INITIAL_SECRET": "initial-value",
                "ROTATED_SECRET": "rotated-value",
                "CROSS_KIND_SECRET": "cross-kind-sensitive-value",
                "UNREFERENCED_SECRET": "unreferenced-sensitive-value",
                "AWS_SECRET_ACCESS_KEY": "aws-sensitive-value",
                "GITHUB_TOKEN": "github-sensitive-value",
                "MELIX_HTTP_HOST": "0.0.0.0",
                "MELIX_GATEWAY_AUTH_MODE": "api-key",
                "MELIX_GATEWAY_API_KEYS_JSON": '[{"id":"test","secret":"gateway-secret"}]',
                "MELIX_GATEWAY_BEARER_TOKEN": "gateway-bearer-secret",
                "MELIX_API_KEY": "parent-api-key",
                "MELIX_HF_TOKEN": "parent-hf-token",
                "MELIX_HUGGINGFACE_TOKEN": "parent-huggingface-token",
                "MELIX_MCP_HIGH_RISK_ALLOWLIST": "trusted.exec",
                "MELIX_PHASE8_WINDOW_UI_ACCEPTANCE": "1",
                "MELIX_MENU_BAR_TERMINATION_MODE": "terminate-bundled-workers",
                "MELIX_BATCH_RUN_ID": "cli-batch-run",
                "MELIX_COMPUTER_BROKER_CAPABILITY_FILE": "parent-capability-path",
                "MELIX_COMPUTER_BROKER_DIR": "parent-broker-dir",
                "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE": "parent-private-key-path",
                "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE": "parent-public-key-path",
                "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT": "1",
            },
            pass_fds=(inherited_fd,),
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        os.close(inherited_fd)

    if rotation_mode == "cross-kind-reference":
        assert result.returncode != 0
        assert "invalid" in result.stderr
        assert not any(record_dir.iterdir())
        assert "CROSS_KIND_SECRET" not in result.stderr
        assert "cross-kind-sensitive-value" not in result.stderr
        return

    if rotation_mode == "new-key":
        assert result.returncode != 0
        assert "restart Melix" in result.stderr
        assert not (record_dir / "app.json").exists()
        python_record = json.loads(
            (record_dir / "python-worker.json").read_text(encoding="utf-8")
        )
        assert python_record["environment"]["INITIAL_SECRET"] == "initial-value"
        assert python_record["environment"]["ROTATED_SECRET"] is None
        assert python_record["environment"]["MELIX_MCP_CREDENTIAL_ENV_KEYS"] == (
            "INITIAL_SECRET"
        )
        for unreferenced_key in (
            "UNREFERENCED_SECRET",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
        ):
            assert python_record["environment"][unreferenced_key] is None
        assert "ROTATED_SECRET" not in result.stderr
        assert "rotated-value" not in result.stderr
        assert "parent-private-key-path" not in result.stderr
        failed_socket_root = Path(python_record["socket_root"]["path"])
        deadline = time.monotonic() + 5
        while failed_socket_root.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not failed_socket_root.exists()
        return

    if rotation_mode == "cleanup-residue":
        assert result.returncode == 1, result.stderr
    else:
        assert result.returncode == 0, result.stderr
    records = {
        role: json.loads((record_dir / f"{role}.json").read_text(encoding="utf-8"))
        for role in ("swift-worker", "python-worker", "control-plane", "broker", "app")
    }
    active_runtime_args = json.loads(
        (record_dir / "active-runtime.json").read_text(encoding="utf-8")
    )["args"]
    assert int(
        active_runtime_args[active_runtime_args.index("--app-process-id") + 1]
    ) == records["app"]["pid"]
    if rotation_mode == "no-credentials":
        assert records["python-worker"]["environment"]["INITIAL_SECRET"] is None
        assert records["python-worker"]["environment"]["ROTATED_SECRET"] is None
        assert records["python-worker"]["environment"]["MELIX_MCP_CREDENTIAL_ENV_KEYS"] == ""
    else:
        assert records["python-worker"]["environment"]["INITIAL_SECRET"] == "initial-value"
        assert records["python-worker"]["environment"]["ROTATED_SECRET"] == "rotated-value"
        assert records["python-worker"]["environment"]["MELIX_MCP_CREDENTIAL_ENV_KEYS"] == (
            "INITIAL_SECRET,ROTATED_SECRET"
        )
    for unreferenced_key in (
        "UNREFERENCED_SECRET",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    ):
        assert all(
            record["environment"][unreferenced_key] is None
            for record in records.values()
        )
    assert records["python-worker"]["fds"] == []
    for role in ("swift-worker", "control-plane", "broker", "app"):
        assert records[role]["environment"]["INITIAL_SECRET"] is None
    assert records["swift-worker"]["environment"]["ROTATED_SECRET"] is None
    for role in ("control-plane", "broker", "app"):
        assert records[role]["environment"]["ROTATED_SECRET"] is None
    assert records["swift-worker"]["fds"] == []
    assert records["broker"]["fds"] == []
    assert records["app"]["fds"] == []
    assert records["control-plane"]["fds"] == [3, 4]
    assert records["control-plane"]["environment"]["MELIX_HTTP_HOST"] == "0.0.0.0"
    assert records["control-plane"]["environment"]["MELIX_MCP_CONFIG_PATH"] == str(config_path)
    assert records["control-plane"]["environment"]["MELIX_GATEWAY_AUTH_MODE"] == "api-key"
    assert "gateway-secret" in records["control-plane"]["environment"]["MELIX_GATEWAY_API_KEYS_JSON"]
    assert records["control-plane"]["environment"]["MELIX_GATEWAY_BEARER_TOKEN"] == (
        "gateway-bearer-secret"
    )
    assert records["control-plane"]["environment"]["MELIX_MCP_HIGH_RISK_ALLOWLIST"] == "trusted.exec"
    assert records["app"]["environment"]["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE"] == "1"
    assert records["app"]["environment"]["MELIX_MENU_BAR_TERMINATION_MODE"] == (
        "terminate-bundled-workers"
    )
    assert records["app"]["environment"]["MELIX_BATCH_RUN_ID"] == "cli-batch-run"
    for pid_key in (
        "MELIX_CONTROL_PLANE_PID",
        "MELIX_SWIFT_WORKER_PID",
        "MELIX_PYTHON_WORKER_PID",
    ):
        assert int(records["app"]["environment"][pid_key]) > 0
    assert records["swift-worker"]["environment"]["MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT"] == "1"
    for role in ("swift-worker", "python-worker", "broker", "app"):
        for control_plane_only_key in (
            "MELIX_GATEWAY_AUTH_MODE",
            "MELIX_GATEWAY_API_KEYS_JSON",
            "MELIX_GATEWAY_BEARER_TOKEN",
            "MELIX_MCP_HIGH_RISK_ALLOWLIST",
        ):
            assert records[role]["environment"].get(control_plane_only_key) is None
    for role in records.values():
        for strip_only_key in STRIP_ONLY_RESERVED_ENVIRONMENT_KEYS:
            assert role["environment"].get(strip_only_key) is None
        for internal_key in (
            "MELIX_COMPUTER_BROKER_CAPABILITY_FILE",
            "MELIX_COMPUTER_BROKER_DIR",
            "MELIX_COMPUTER_BROKER_PRIVATE_KEY_FILE",
            "MELIX_COMPUTER_BROKER_PUBLIC_KEY_FILE",
        ):
            assert role["environment"].get(internal_key) is None

    socket_paths = (
        records["python-worker"]["environment"]["MELIX_WORKER_SOCKET_PATH"],
        records["swift-worker"]["environment"]["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"],
        records["control-plane"]["environment"]["MELIX_CONTROL_PLANE_SOCKET_PATH"],
        records["broker"]["effective_socket_path"],
    )
    assert all(path is not None for path in socket_paths)
    assert all(
        len(os.fsencode(path)) <= DARWIN_UNIX_SOCKET_PATH_MAX_BYTES
        for path in socket_paths
        if path is not None
    )
    socket_roots = {
        Path(path).parent.parent
        if path.endswith("/computer-broker/broker.sock")
        else Path(path).parent
        for path in socket_paths
        if path is not None
    }
    assert len(socket_roots) == 1
    socket_root = socket_roots.pop()
    assert socket_root.parent == Path("/tmp")
    assert socket_root.name.startswith(f"melix-{os.geteuid()}-boundary-test.")
    assert all(
        record["socket_root"]
        == {"path": os.fspath(socket_root), "uid": os.geteuid(), "mode": 0o700}
        for record in records.values()
    )
    if rotation_mode == "cleanup-residue":
        residue_path = socket_root / "unexpected-residue"

        def remove_fixture_residue() -> None:
            residue_path.unlink(missing_ok=True)
            if socket_root.exists():
                socket_root.rmdir()

        request.addfinalizer(remove_fixture_residue)
        cleanup_log = melix_home / "logs/launcher-cleanup.log"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cleanup_log.exists() and "retained private runtime directory" in cleanup_log.read_text(
                encoding="utf-8"
            ):
                break
            time.sleep(0.02)
        assert residue_path.read_text(encoding="utf-8") == "fixture residue\n"
        cleanup_text = cleanup_log.read_text(encoding="utf-8")
        assert f"Melix retained private runtime directory {socket_root}" in cleanup_text
        assert "inspect this log before relaunching" in cleanup_text
        assert "run_pending_traps" not in cleanup_text
        return

    deadline = time.monotonic() + 5
    while socket_root.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not socket_root.exists()
    if sibling_socket_root is not None:
        assert sibling_socket_root.exists()


def test_render_native_launcher_source_execs_packaged_launcher_script() -> None:
    source = render_native_launcher_source(script_relative_path="../Resources/Melix.sh")

    assert '#include <mach-o/dyld.h>' in source
    assert '"%s/../Resources/Melix.sh"' in source
    assert 'scriptArgv[0] = "/bin/bash"' in source
    assert "scriptArgv[1] = scriptPath" in source
    assert 'execv("/bin/bash", scriptArgv)' in source


def test_resolve_python_runtime_root_resolves_from_python_executable(tmp_path: Path) -> None:
    runtime_root = tmp_path / "python-runtime"
    (runtime_root / "bin").mkdir(parents=True)
    executable = runtime_root / "bin/python3"
    executable.write_text("", encoding="utf-8")

    assert resolve_python_runtime_root(executable) == runtime_root


def test_resolve_site_packages_root_finds_virtualenv_site_packages(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    site_packages = repo_root / ".venv/lib/python3.13/site-packages"
    site_packages.mkdir(parents=True)

    assert resolve_site_packages_root(repo_root) == site_packages


def test_resolve_site_packages_root_requires_virtualenv_site_packages(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    try:
        resolve_site_packages_root(repo_root)
    except FileNotFoundError as error:
        assert str(repo_root / ".venv/lib") in str(error)
    else:
        raise AssertionError("expected resolve_site_packages_root() to fail without site-packages")


def test_resolve_site_packages_root_skips_non_site_package_entries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    lib_root = repo_root / ".venv/lib"
    lib_root.mkdir(parents=True)
    (lib_root / "not-python").mkdir()
    (lib_root / "python-not-a-directory").write_text("", encoding="utf-8")
    (lib_root / "python3.12").mkdir()

    try:
        resolve_site_packages_root(repo_root)
    except FileNotFoundError as error:
        assert str(lib_root) in str(error)
    else:
        raise AssertionError("expected resolve_site_packages_root() to fail without site-packages")


def test_write_unsigned_macos_app_bundle_writes_self_contained_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "services/mlx-worker-python/worker").mkdir(parents=True)
    top20_fixture_root = (
        repo_root
        / "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1"
    )
    benchmark_fixture_root = (
        repo_root
        / "services/mlx-worker-python/fixtures/benchmark/agentic-image.dev.v1"
    )
    full_fixture_root = (
        repo_root
        / "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.full.v1"
    )
    top20_fixture_root.mkdir(parents=True)
    benchmark_fixture_root.mkdir(parents=True)
    full_fixture_root.mkdir(parents=True)
    (repo_root / "packages/protocol/python").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "services/mlx-worker-python/worker/bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/worker/control_plane_bridge.py").write_text("print('bridge')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
    (top20_fixture_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v2",
                "dataset_id": "top200.event-extraction.top20.v1",
                "suite_id": "event_extraction",
                "sample_count": 20,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (top20_fixture_root / "samples.jsonl").write_text(
        "".join(
            json.dumps({"dialogue_id": str(index + 1), "dialogue": ["line"], "events": [{"action": ["test"]}]})
            + "\n"
            for index in range(20)
        ),
        encoding="utf-8",
    )
    (benchmark_fixture_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.benchmark_fixture_package.v1",
                "fixture_package_id": "agentic-image.dev.v1",
                "suite_id": "agentic_image",
                "sample_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (benchmark_fixture_root / "samples.jsonl").write_text(
        json.dumps({"prompt": "Inspect the image.", "tool_calls": []}) + "\n",
        encoding="utf-8",
    )
    (full_fixture_root / "samples.jsonl").write_text(
        "".join(
            json.dumps({"dialogue_id": str(index + 1), "dialogue": ["line"], "events": [{"action": ["test"]}]})
            + "\n"
            for index in range(200)
        ),
        encoding="utf-8",
    )
    (repo_root / "services/mlx-worker-python/fixtures/evaluation/top200_final.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (repo_root / "packages/protocol/python/__init__.py").write_text("", encoding="utf-8")
    (repo_root / "scripts/wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    menubar = tmp_path / "melix-menubar"
    cli = tmp_path / "melix"
    control_plane = tmp_path / "melix-control-plane"
    swift_worker = tmp_path / "swift-worker-release/melix-text-worker-swift"
    computer_broker = tmp_path / "melix-computer-broker"
    for executable in (menubar, cli, control_plane, swift_worker, computer_broker):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)
    swift_mlx_metallib = tmp_path / "swift-mlx-runtime/mlx.metallib"
    swift_mlx_metallib.parent.mkdir()
    swift_mlx_metallib.write_bytes(b"matching-swift-mlx-metallib")
    swiftpm_resource_bundle = tmp_path / "MelixMacOSMenubar_AppMain.bundle"
    swiftpm_resource_bundle.mkdir()
    (swiftpm_resource_bundle / "melix-status-template.png").write_bytes(b"png")
    swift_worker_resource_bundle = swift_worker.parent / "swift-transformers_Hub.bundle"
    swift_worker_resource_bundle.mkdir()
    (swift_worker_resource_bundle / "gpt2_tokenizer_config.json").write_text("{}\n", encoding="utf-8")

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)
    icon_file = tmp_path / "MelixAppIcon.icns"
    icon_file.write_bytes(b"icns")
    sparkle_framework = tmp_path / "Sparkle.framework"
    sparkle_version_root = sparkle_framework / "Versions/B"
    sparkle_resources = sparkle_version_root / "Resources"
    sparkle_resources.mkdir(parents=True)
    (sparkle_version_root / "Sparkle").write_bytes(b"sparkle-framework")
    (sparkle_version_root / "Autoupdate").write_bytes(b"sparkle-autoupdate")
    (sparkle_version_root / "Updater.app").mkdir()
    (sparkle_version_root / "XPCServices/Downloader.xpc").mkdir(parents=True)
    (sparkle_version_root / "XPCServices/Installer.xpc").mkdir()
    (sparkle_resources / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": "2.9.4"})
    )
    sparkle_public_key = base64.b64encode(bytes(range(32))).decode("ascii")
    python_site_packages = tmp_path / "python-site-packages"
    python_site_packages.mkdir()
    (python_site_packages / "grpc.py").write_text("", encoding="utf-8")
    launcher_compile_calls: list[tuple[Path, Path]] = []

    def fake_compile_native_launcher(source_path: Path, output_path: Path) -> None:
        launcher_compile_calls.append((source_path, output_path))
        assert '"%s/../Resources/Melix.sh"' in source_path.read_text(encoding="utf-8")
        output_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(
        macos_app_bundle_module,
        "compile_native_launcher",
        fake_compile_native_launcher,
    )

    manifest = write_unsigned_macos_app_bundle(
        repo_root=repo_root,
        executable_path=menubar,
        cli_executable_path=cli,
        control_plane_executable_path=control_plane,
        swift_text_worker_executable_path=swift_worker,
        computer_broker_executable_path=computer_broker,
        swift_mlx_metallib_path=swift_mlx_metallib,
        swift_mlx_metallib_version="0.31.1",
        python_runtime_root=python_runtime,
        python_site_packages_path=python_site_packages,
        output_path=tmp_path / "Melix.app",
        bundle_id="io.melix.menubar",
        packaging_target_id="macos_app_bundle_github_release",
        icon_source_path=icon_file,
        http_bind_host="0.0.0.0",
        http_port=12436,
        insecure_http_hosts=("192.0.2.10",),
        sparkle_framework_path=sparkle_framework,
        sparkle_feed_url=(
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
        ),
            sparkle_public_ed_key=sparkle_public_key,
            code_signing_mode="stable_self_signed",
            code_signing_certificate_sha256="a" * 64,
            code_signing_certificate_sha1="0123456789abcdef0123456789abcdef01234567",
        code_signing_authority="Melix GitHub Release Signing",
    )

    app_path = Path(manifest["app_path"])
    assert app_path.exists() is True
    assert Path(manifest["bundled_cli_binary_path"]).exists() is True
    assert Path(manifest["bundled_control_plane_binary_path"]).exists() is True
    assert Path(manifest["bundled_swift_worker_binary_path"]).exists() is True
    assert Path(manifest["bundled_computer_broker_binary_path"]).exists() is True
    broker_plist_path = Path(manifest["bundled_computer_broker_plist_path"])
    assert broker_plist_path.exists() is True
    broker_plist = plistlib.loads(broker_plist_path.read_bytes())
    assert broker_plist == {
        "CFBundleExecutable": "melix-computer-broker",
        "CFBundleIdentifier": "io.melix.menubar.computer-broker",
        "CFBundleName": "MelixComputerUseBroker",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSBackgroundOnly": True,
        "LSMinimumSystemVersion": "15.0",
    }
    bundled_swift_mlx_metallib = Path(manifest["bundled_swift_mlx_metallib_path"])
    swift_mlx_metallib_link = app_path / "Contents/Resources/mlx.metallib"
    assert bundled_swift_mlx_metallib.read_bytes() == b"matching-swift-mlx-metallib"
    assert swift_mlx_metallib_link.is_symlink()
    assert swift_mlx_metallib_link.readlink() == Path("swift-mlx/mlx.metallib")
    assert swift_mlx_metallib_link.resolve() == bundled_swift_mlx_metallib.resolve()
    assert manifest["swift_mlx_metallib_version"] == "0.31.1"
    assert Path(manifest["bundled_python_runtime_path"]).exists() is True
    assert Path(manifest["bundled_site_packages_path"]).exists() is True
    bundled_repo_root = Path(manifest["bundled_repo_root_path"])
    assert bundled_repo_root.joinpath("services/mlx-worker-python/worker/bootstrap.py").exists() is True
    bundled_top20 = bundled_repo_root / "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1"
    assert bundled_top20.joinpath("manifest.json").exists() is True
    assert len(bundled_top20.joinpath("samples.jsonl").read_text(encoding="utf-8").splitlines()) == 20
    bundled_agentic_image = bundled_repo_root / "services/mlx-worker-python/fixtures/benchmark/agentic-image.dev.v1"
    assert bundled_agentic_image.joinpath("manifest.json").exists() is True
    assert bundled_agentic_image.joinpath("samples.jsonl").exists() is True
    assert bundled_repo_root.joinpath(
        "services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.full.v1"
    ).exists() is False
    assert bundled_repo_root.joinpath("services/mlx-worker-python/fixtures/evaluation/top200_final.jsonl").exists() is False
    assert Path(manifest["bundled_icon_path"]).exists() is True
    bundled_sparkle_framework = Path(manifest["bundled_sparkle_framework_path"])
    assert bundled_sparkle_framework.joinpath("Versions/B/Sparkle").is_file()
    assert manifest["sparkle_framework_version"] == "2.9.4"
    assert manifest["sparkle_updates_enabled"] is True
    assert (app_path / "MelixMacOSMenubar_AppMain.bundle").exists() is False
    assert (
        app_path / "Contents/Resources/MelixMacOSMenubar_AppMain.bundle/melix-status-template.png"
    ).is_file()
    assert (
        app_path / "Contents/Resources/swift-transformers_Hub.bundle/gpt2_tokenizer_config.json"
    ).is_file()
    assert manifest["bundled_swiftpm_resource_bundle_paths"] == [
        str(app_path / "Contents/Resources/MelixMacOSMenubar_AppMain.bundle"),
        str(app_path / "Contents/Resources/swift-transformers_Hub.bundle"),
    ]
    assert Path(manifest["packaging_target_manifest_path"]).exists() is True
    assert Path(manifest["launcher_path"]).is_file() is True
    assert launcher_compile_calls == [
        (app_path / "Contents/MacOS/MelixLauncher.c", app_path / "Contents/MacOS/Melix"),
    ]
    launcher = Path(manifest["launcher_script_path"]).read_text(encoding="utf-8")
    assert "worker.bootstrap" in launcher
    assert 'export MELIX_CLI="$RESOURCES_DIR/melix"' in launcher
    assert '"$RESOURCES_DIR/melix-control-plane"' in launcher
    assert "melix-text-worker-swift" in launcher
    assert 'export MELIX_MENU_BAR_STARTUP_SURFACE="console"' in launcher
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in launcher
    assert 'export MELIX_APP_BUNDLE_PATH="$(cd "$CONTENTS_DIR/.." && pwd)"' in launcher
    assert '"$MELIX_RUNTIME_DIR/python-bytecode-cache"' in launcher
    assert "export MELIX_SWIFT_WORKER_PID" not in launcher
    assert "export MELIX_PYTHON_WORKER_PID" not in launcher
    assert "export MELIX_CONTROL_PLANE_PID" not in launcher
    assert 'http://$MELIX_HTTP_CONNECT_HOST:$MELIX_HTTP_PORT/health' in launcher
    assert '-m worker.productization.active_runtime' in launcher
    assert 'MELIX_CONTROL_PLANE_PID="$MELIX_CONTROL_PLANE_PID"' in launcher
    assert 'MELIX_SWIFT_WORKER_PID="$MELIX_SWIFT_WORKER_PID"' in launcher
    assert 'MELIX_PYTHON_WORKER_PID="$MELIX_PYTHON_WORKER_PID"' in launcher
    assert (
        'MELIX_MCP_CREDENTIAL_ENV_KEYS="$(join_frozen_mcp_credential_keys)" '
        '"$CONTENTS_DIR/MacOS/melix-menubar" "$@" &'
    ) in launcher
    plist_payload = plistlib.loads(Path(manifest["plist_path"]).read_bytes())
    assert plist_payload["CFBundleIdentifier"] == "io.melix.menubar"
    assert plist_payload["CFBundleIconFile"] == "MelixAppIcon.icns"
    assert plist_payload["SUFeedURL"] == (
        "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
    )
    assert plist_payload["SUPublicEDKey"] == sparkle_public_key
    assert plist_payload["SURequireSignedFeed"] is True
    assert plist_payload["SUAllowsAutomaticUpdates"] is False
    assert plist_payload["NSAppTransportSecurity"] == {
        "NSAllowsLocalNetworking": True,
        "NSExceptionDomains": {
            "192.0.2.10": {
                "NSExceptionAllowsInsecureHTTPLoads": True,
            },
        },
    }
    assert manifest["ats_insecure_http_hosts"] == ["192.0.2.10"]
    target_manifest = json.loads(
        Path(manifest["packaging_target_manifest_path"]).read_text(encoding="utf-8")
    )
    assert target_manifest["ats_insecure_http_hosts"] == ["192.0.2.10"]
    assert plist_payload["NSLocalNetworkUsageDescription"] == (
        "Connect to remote AI providers that you configure on your local network or tailnet."
    )
    assert "LSUIElement" not in plist_payload
    env_script = Path(manifest["embedded_env_script_path"]).read_text(encoding="utf-8")
    assert (
        'export MELIX_PACKAGING_TARGET_ID="macos_app_bundle_github_release"'
        in env_script
    )
    assert 'export MELIX_PRODUCT_VERSION="0.1.0"' in env_script
    assert 'export MELIX_HTTP_HOST="${MELIX_HTTP_HOST:-0.0.0.0}"' in env_script
    assert 'export MELIX_HTTP_CONNECT_HOST="${MELIX_HTTP_CONNECT_HOST:-127.0.0.1}"' in env_script
    assert 'export MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY="environment"' in env_script
    assert "MELIX_APP_SUPPORT_DIR" not in env_script
    assert 'export MELIX_MODEL_OPS_JOBS_ROOT="${MELIX_MODEL_OPS_JOBS_ROOT:-$MELIX_HOME/jobs/model-ops}"' in env_script
    assert 'export MELIX_EVALUATION_JOBS_ROOT="${MELIX_EVALUATION_JOBS_ROOT:-$MELIX_HOME/jobs/evaluation}"' in env_script
    target_payload = json.loads(Path(manifest["packaging_target_manifest_path"]).read_text(encoding="utf-8"))
    assert target_payload["packaging_target_id"] == "macos_app_bundle_github_release"
    assert target_payload["logical_product_identity"] == "io.melix"
    assert target_payload["http_bind_host"] == "0.0.0.0"
    assert target_payload["http_connect_host"] == "127.0.0.1"
    assert target_payload["swift_mlx_metallib_path"] == "mlx.metallib"
    assert target_payload["swift_mlx_metallib_version"] == "0.31.1"
    assert target_payload["code_signing"] == {
        "mode": "stable_self_signed",
        "expected_certificate_sha256": "a" * 64,
        "expected_certificate_sha1": "0123456789abcdef0123456789abcdef01234567",
        "expected_authority": "Melix GitHub Release Signing",
    }
    assert target_payload["sparkle_updates"]["enabled"] is True
    assert target_payload["sparkle_updates"]["framework_version"] == "2.9.4"
    assert target_payload["sparkle_updates"]["framework_bytes"] > 0
    assert target_payload["sparkle_updates"]["public_key_sha256"] == hashlib.sha256(
        bytes(range(32))
    ).hexdigest()
    assert "private" not in json.dumps(target_payload["sparkle_updates"]).lower()
    assert target_payload["health_probe_url"] == "http://127.0.0.1:12436/health"
    assert manifest["service_base_url"] == "http://127.0.0.1:12436/v1"
    timings = manifest["timings"]
    for key in (
        "copy_app_binary_seconds",
        "copy_swift_worker_binary_seconds",
        "copy_swift_mlx_metallib_seconds",
        "copy_icon_seconds",
        "copy_sparkle_framework_seconds",
        "configure_sparkle_rpath_seconds",
        "copy_python_runtime_seconds",
        "copy_python_site_packages_seconds",
        "copy_swiftpm_resource_bundles_seconds",
        "copy_repo_subset_seconds",
        "write_metadata_seconds",
        "compile_launcher_seconds",
        "chmod_seconds",
        "write_total_seconds",
    ):
        assert isinstance(timings[key], float)
        assert timings[key] >= 0.0


def test_write_unsigned_macos_app_bundle_slims_copied_runtime_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "services/mlx-worker-python/worker").mkdir(parents=True)
    (repo_root / "packages/protocol/python").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "services/mlx-worker-python/worker/bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/worker/control_plane_bridge.py").write_text("print('bridge')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
    (repo_root / "packages/protocol/python/__init__.py").write_text("", encoding="utf-8")
    (repo_root / "scripts/wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")

    menubar = tmp_path / "melix-menubar"
    cli = tmp_path / "melix"
    control_plane = tmp_path / "melix-control-plane"
    swift_worker = tmp_path / "melix-text-worker-swift"
    computer_broker = tmp_path / "melix-computer-broker"
    for executable in (menubar, cli, control_plane, swift_worker, computer_broker):
        executable.write_text("#!/usr/bin/env bash\necho debug-symbols\n", encoding="utf-8")
        executable.chmod(0o755)

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python-debug-symbols\n", encoding="utf-8")
    python_executable.chmod(0o755)
    runtime_dylib = python_runtime / "lib/libpython3.12.dylib"
    runtime_dylib.parent.mkdir(parents=True)
    runtime_dylib.write_text("native-debug-symbols\n", encoding="utf-8")
    runtime_include = python_runtime / "include/python3.12"
    runtime_include.mkdir(parents=True)
    (runtime_include / "Python.h").write_text("not needed by packaged runtime\n", encoding="utf-8")
    runtime_static_archive = python_runtime / "lib/libpython3.12.a"
    runtime_static_archive.write_text("not needed by packaged runtime\n", encoding="utf-8")
    runtime_ensurepip = python_runtime / "lib/python3.12/ensurepip/_bundled"
    runtime_ensurepip.mkdir(parents=True)
    (runtime_ensurepip / "pip-25.0.1-py3-none-any.whl").write_text(
        "not needed by packaged runtime\n",
        encoding="utf-8",
    )
    runtime_pycache = python_runtime / "lib/python3.12/json/__pycache__"
    runtime_pycache.mkdir(parents=True)
    (runtime_pycache / "decoder.cpython-312.pyc").write_bytes(b"not needed by packaged runtime\n")

    python_site_packages = tmp_path / "python-site-packages"
    native_package = python_site_packages / "nativepkg"
    native_package.mkdir(parents=True)
    native_extension = native_package / "module.cpython-312-darwin.so"
    native_extension.write_text("native-debug-symbols\n", encoding="utf-8")
    native_extension.chmod(0o755)
    external_native_extension = tmp_path / "external-module.cpython-312-darwin.so"
    external_native_extension.write_text("external-native-debug-symbols\n", encoding="utf-8")
    (native_package / "linked-module.cpython-312-darwin.so").symlink_to(external_native_extension)
    for pruned_dir in ("tests", "test", "testing", "docs", "doc", "__pycache__"):
        path = native_package / pruned_dir
        path.mkdir()
        (path / "fixture.txt").write_text("not needed at runtime\n", encoding="utf-8")
    retained_source = native_package / "runtime.py"
    retained_source.write_text("VALUE = 'kept'\n", encoding="utf-8")
    swift_mlx_metallib = tmp_path / "swift-mlx-runtime/mlx.metallib"
    swift_mlx_metallib.parent.mkdir()
    swift_mlx_metallib.write_bytes(b"matching-swift-mlx-metallib")

    icon_file = tmp_path / "MelixAppIcon.icns"
    icon_file.write_bytes(b"icns")
    strip_calls: list[str] = []

    def fake_which(name: str) -> str | None:
        if name == "strip":
            return "/usr/bin/strip"
        if name == "xcrun":
            return "/usr/bin/xcrun"
        return None

    def fake_run(command: list[str], check: bool, **kwargs: object):
        if command[0] == "otool":
            return type("Completed", (), {"stdout": ""})()
        if command[0] == "/usr/bin/strip":
            target = Path(command[-1])
            strip_calls.append(target.name)
            target.write_text(target.read_text(encoding="utf-8").replace("debug-symbols", "stripped"), encoding="utf-8")
            return None
        raise AssertionError(f"unexpected subprocess command: {command}")

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", fake_which)
    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        macos_app_bundle_module,
        "compile_native_launcher",
        lambda source_path, output_path: output_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8"),
    )

    manifest = write_unsigned_macos_app_bundle(
        repo_root=repo_root,
        executable_path=menubar,
        cli_executable_path=cli,
        control_plane_executable_path=control_plane,
        swift_text_worker_executable_path=swift_worker,
        computer_broker_executable_path=computer_broker,
        swift_mlx_metallib_path=swift_mlx_metallib,
        swift_mlx_metallib_version="0.31.1",
        python_runtime_root=python_runtime,
        python_site_packages_path=python_site_packages,
        output_path=tmp_path / "Melix.app",
        icon_source_path=icon_file,
    )

    resources = Path(manifest["resources_path"])
    bundled_runtime = resources / "python-runtime"
    bundled_package = resources / "python-site-packages/nativepkg"
    assert (bundled_runtime / "include").exists() is False
    assert (bundled_runtime / "lib/libpython3.12.a").exists() is False
    assert (bundled_runtime / "lib/python3.12/ensurepip").exists() is False
    assert (bundled_runtime / "lib/python3.12/json/__pycache__").exists() is False
    assert (bundled_package / "runtime.py").is_file()
    for pruned_dir in ("tests", "test", "testing", "docs", "doc", "__pycache__"):
        assert (bundled_package / pruned_dir).exists() is False
    assert "melix-menubar" in strip_calls
    assert "melix" in strip_calls
    assert "melix-control-plane" in strip_calls
    assert "melix-text-worker-swift" in strip_calls
    assert "melix-computer-broker" in strip_calls
    assert "python3" in strip_calls
    assert "libpython3.12.dylib" in strip_calls
    assert "module.cpython-312-darwin.so" in strip_calls
    assert "linked-module.cpython-312-darwin.so" not in strip_calls
    assert external_native_extension.read_text(encoding="utf-8") == "external-native-debug-symbols\n"
    assert (native_package / "tests").is_dir()
    slimming = manifest["slimming"]
    assert slimming["swift_binaries_stripped"] == 5
    assert slimming["python_native_binaries_stripped"] == 3
    assert slimming["python_package_directories_pruned"] == 6
    assert slimming["python_runtime_baggage_bytes_saved"] > 0
    assert slimming["bytes_saved"] > 0
    timings = manifest["timings"]
    assert isinstance(timings["strip_swift_binaries_seconds"], float)
    assert isinstance(timings["strip_python_native_binaries_seconds"], float)
    assert isinstance(timings["prune_python_package_baggage_seconds"], float)
    assert isinstance(timings["prune_python_runtime_baggage_seconds"], float)


def test_bundle_slimming_helpers_cover_runtime_edge_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    site_packages = tmp_path / "site-packages"
    runtime_bin = runtime / "bin"
    runtime_lib = runtime / "lib/python3.12"
    site_package = site_packages / "nativepkg"
    runtime_bin.mkdir(parents=True)
    runtime_lib.mkdir(parents=True)
    site_package.mkdir(parents=True)

    python_versioned = runtime_bin / "python3.12"
    python_versioned.write_text("python-debug-symbols\n", encoding="utf-8")
    runtime_so = runtime_lib / "_socket.cpython-312-darwin.so"
    runtime_so.write_text("native-debug-symbols\n", encoding="utf-8")
    site_so = site_package / "module.cpython-312-darwin.so"
    site_so.write_text("native-debug-symbols\n", encoding="utf-8")
    skipped_runtime_file = runtime / "README.txt"
    skipped_runtime_file.write_text("not native\n", encoding="utf-8")
    skipped_runtime_executable = runtime_lib / "python3.12"
    skipped_runtime_executable.write_text("not in bin\n", encoding="utf-8")

    include_target = tmp_path / "include-target"
    include_target.mkdir()
    include_link = runtime / "include"
    include_link.symlink_to(include_target, target_is_directory=True)
    ensurepip_link_target = tmp_path / "ensurepip-target"
    ensurepip_link_target.mkdir()
    ensurepip_link = runtime_lib / "ensurepip"
    ensurepip_link.symlink_to(ensurepip_link_target, target_is_directory=True)
    pycache = runtime_lib / "__pycache__"
    pycache.mkdir()
    (pycache / "module.pyc").write_bytes(b"cache")
    archive = runtime / "libpython3.12.a"
    archive.write_text("archive\n", encoding="utf-8")
    retained_py = runtime_lib / "runtime.py"
    retained_py.write_text("VALUE = 1\n", encoding="utf-8")

    package_doc_link_target = tmp_path / "doc-target"
    package_doc_link_target.mkdir()
    package_doc_link = site_package / "docs"
    package_doc_link.symlink_to(package_doc_link_target, target_is_directory=True)

    assert _path_size_bytes(site_package) > 0
    assert _path_size_bytes(tmp_path / "missing") == 0

    package_prune = _prune_python_package_baggage(site_packages)
    assert package_prune["directories_pruned"] == 1
    assert package_prune["bytes_saved"] > 0
    assert package_doc_link.exists() is False
    assert package_doc_link_target.is_dir()

    runtime_prune = _prune_python_runtime_baggage(runtime)
    assert runtime_prune["directories_pruned"] == 3
    assert runtime_prune["files_pruned"] == 1
    assert runtime_prune["bytes_saved"] > 0
    assert include_link.exists() is False
    assert include_target.is_dir()
    assert ensurepip_link.exists() is False
    assert ensurepip_link_target.is_dir()
    assert pycache.exists() is False
    assert archive.exists() is False
    assert retained_py.is_file()

    candidates = _iter_python_native_binary_candidates(runtime, site_packages)
    assert python_versioned in candidates
    assert runtime_so in candidates
    assert site_so in candidates
    assert skipped_runtime_file not in candidates
    assert skipped_runtime_executable not in candidates

    def fail_rglob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError("_iter_python_native_binary_candidates() should not allocate Path.rglob() trees")

    def fail_splitext(path: str):  # pragma: no cover - regression guard
        raise AssertionError("_iter_python_native_binary_candidates() should use direct suffix checks")

    def fail_sorted(iterable, *args: object, **kwargs: object):  # pragma: no cover - regression guard
        raise AssertionError("_iter_python_native_binary_candidates() should stream scandir entries")

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    monkeypatch.setattr(macos_app_bundle_module.os.path, "splitext", fail_splitext)
    monkeypatch.setattr(macos_app_bundle_module, "sorted", fail_sorted, raising=False)
    assert set(_iter_python_native_binary_candidates(runtime, site_packages)) == {
        python_versioned,
        runtime_so,
        site_so,
    }

    path_constructor_calls = 0
    real_path = Path

    def counting_path(value: object = ".", *args: object, **kwargs: object) -> Path:
        nonlocal path_constructor_calls
        path_constructor_calls += 1
        return real_path(value, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(macos_app_bundle_module, "Path", counting_path)
    assert set(_iter_python_native_binary_candidates(runtime, site_packages)) == {
        python_versioned,
        runtime_so,
        site_so,
    }
    assert path_constructor_calls == 3

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/strip")

    def fake_strip(command: list[str], check: bool, **kwargs: object) -> None:
        target = Path(command[-1])
        if target == site_so:
            raise macos_app_bundle_module.subprocess.CalledProcessError(returncode=1, cmd=command)
        target.write_text(target.read_text(encoding="utf-8").replace("debug-symbols", "stripped"), encoding="utf-8")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_strip)

    strip_result = _strip_packaged_binaries(
        [
            python_versioned,
            python_versioned,
            runtime_so,
            site_so,
            runtime / "missing.so",
        ]
    )
    assert strip_result["attempted"] == 3
    assert strip_result["stripped"] == 2
    assert strip_result["failed"] == 1
    assert strip_result["bytes_saved"] > 0

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: None)
    unavailable_result = _strip_packaged_binaries([python_versioned])
    assert unavailable_result["strip_available"] is False
    assert unavailable_result["attempted"] == 0


def test_prune_python_package_baggage_uses_scandir_without_os_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_packages = tmp_path / "site-packages"
    package = site_packages / "package"
    nested = package / "nested"
    docs = nested / "docs"
    retained = nested / "runtime.py"
    docs.mkdir(parents=True)
    retained.write_text("VALUE = 1\n", encoding="utf-8")
    (docs / "fixture.txt").write_text("not shipped\n", encoding="utf-8")

    def fail_os_walk(*args: object, **kwargs: object):  # pragma: no cover - regression guard
        raise AssertionError("_prune_python_package_baggage() should stream os.scandir entries")

    monkeypatch.setattr(macos_app_bundle_module.os, "walk", fail_os_walk)

    result = _prune_python_package_baggage(site_packages)

    assert result["directories_pruned"] == 1
    assert result["bytes_saved"] > 0
    assert docs.exists() is False
    assert retained.is_file()


def test_prune_python_package_baggage_tolerates_scan_and_delete_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_packages = tmp_path / "site-packages"
    package = site_packages / "package"
    docs = package / "docs"
    unreadable = package / "unreadable"
    docs.mkdir(parents=True)
    unreadable.mkdir()
    (docs / "fixture.txt").write_text("not shipped\n", encoding="utf-8")

    original_scandir = macos_app_bundle_module.os.scandir
    original_rmtree = macos_app_bundle_module.shutil.rmtree

    class BrokenEntry:
        name = "broken"
        path = str(package / "broken")

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            raise OSError("synthetic entry metadata failure")

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self._entries = entries

        def __enter__(self) -> "FakeScandir":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self):
            return iter(self._entries)

    def fake_scandir(path: Path | str):
        path = Path(path)
        if path == package:
            real_entries = list(original_scandir(path))
            return FakeScandir([BrokenEntry(), *real_entries])
        if path == unreadable:
            raise OSError("synthetic scandir failure")
        return original_scandir(path)

    def flaky_rmtree(path: Path) -> None:
        if path == docs:
            raise OSError("synthetic delete failure")
        original_rmtree(path)

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)
    monkeypatch.setattr(macos_app_bundle_module.shutil, "rmtree", flaky_rmtree)

    assert _prune_python_package_baggage(site_packages) == {
        "directories_pruned": 0,
        "bytes_saved": 0,
    }
    assert docs.is_dir()


def test_prune_python_runtime_baggage_uses_scandir_without_os_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    nested = runtime / "lib/python3.12"
    pycache = nested / "__pycache__"
    retained = nested / "runtime.py"
    archive = runtime / "libpython3.12.a"
    pycache.mkdir(parents=True)
    (pycache / "module.pyc").write_bytes(b"cache")
    retained.write_text("VALUE = 1\n", encoding="utf-8")
    archive.write_text("archive\n", encoding="utf-8")

    def fail_os_walk(*args: object, **kwargs: object):  # pragma: no cover - regression guard
        raise AssertionError("_prune_python_runtime_baggage() should stream os.scandir entries")

    monkeypatch.setattr(macos_app_bundle_module.os, "walk", fail_os_walk)

    result = _prune_python_runtime_baggage(runtime)

    assert result["directories_pruned"] == 1
    assert result["files_pruned"] == 1
    assert result["bytes_saved"] > 0
    assert pycache.exists() is False
    assert archive.exists() is False
    assert retained.is_file()


def test_prune_python_runtime_baggage_tolerates_scan_and_metadata_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    nested = runtime / "lib/python3.12"
    pycache = nested / "__pycache__"
    unreadable = nested / "unreadable"
    archive = nested / "libpython3.12.a"
    retained = nested / "runtime.py"
    pycache.mkdir(parents=True)
    unreadable.mkdir()
    archive.write_text("archive\n", encoding="utf-8")
    retained.write_text("VALUE = 1\n", encoding="utf-8")

    original_scandir = macos_app_bundle_module.os.scandir
    original_rmtree = macos_app_bundle_module.shutil.rmtree

    class BrokenEntry:
        name = "broken"
        path = str(nested / "broken")

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            raise OSError("synthetic runtime metadata failure")

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self._entries = entries

        def __enter__(self) -> "FakeScandir":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self):
            return iter(self._entries)

    def fake_scandir(path: Path | str):
        path = Path(path)
        if path == nested:
            real_entries = list(original_scandir(path))
            return FakeScandir([BrokenEntry(), *real_entries])
        if path == unreadable:
            raise OSError("synthetic runtime scandir failure")
        return original_scandir(path)

    def flaky_rmtree(path: Path) -> None:
        if path == pycache:
            raise OSError("synthetic runtime delete failure")
        original_rmtree(path)

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)
    monkeypatch.setattr(macos_app_bundle_module.shutil, "rmtree", flaky_rmtree)

    result = _prune_python_runtime_baggage(runtime)

    assert result["directories_pruned"] == 0
    assert result["files_pruned"] == 1
    assert result["bytes_saved"] > 0
    assert pycache.is_dir()
    assert archive.exists() is False
    assert retained.is_file()


def test_prune_python_runtime_baggage_tolerates_file_unlink_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    nested = runtime / "lib/python3.12"
    nested.mkdir(parents=True)
    non_directory_pycache = nested / "__pycache__"
    archive = nested / "libpython3.12.a"
    bytecode = nested / "module.pyc"
    non_directory_pycache.write_text("not a directory\n", encoding="utf-8")
    archive.write_text("archive\n", encoding="utf-8")
    bytecode.write_bytes(b"cache")
    expected_bytes_saved = archive.stat().st_size + bytecode.stat().st_size

    original_unlink = macos_app_bundle_module.os.unlink

    def flaky_unlink(path: str) -> None:
        if Path(path) == archive:
            raise OSError("synthetic runtime file unlink failure")
        original_unlink(path)

    monkeypatch.setattr(macos_app_bundle_module.os, "unlink", flaky_unlink)

    result = _prune_python_runtime_baggage(runtime)

    assert result["directories_pruned"] == 0
    assert result["files_pruned"] == 1
    assert result["bytes_saved"] == expected_bytes_saved
    assert non_directory_pycache.is_file()
    assert archive.is_file()
    assert bytecode.exists() is False


def test_iter_python_native_binary_candidates_tolerates_scandir_metadata_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    site_packages = tmp_path / "site-packages"
    runtime.mkdir()
    site_packages.mkdir()

    class BrokenEntry:
        name = "broken.so"
        path = str(runtime / "broken.so")

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            raise OSError("synthetic dir metadata failure")

        def is_symlink(self) -> bool:  # pragma: no cover - guarded by is_dir failure
            raise AssertionError("is_symlink should not run after is_dir failure")

        def is_file(self, *, follow_symlinks: bool) -> bool:  # pragma: no cover
            raise AssertionError("is_file should not run after is_dir failure")

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self._entries = entries

        def __enter__(self) -> list[object]:
            return self._entries

        def __exit__(self, *args: object) -> None:
            return None

    def fake_scandir(path: Path):
        if path == runtime:
            return FakeScandir([BrokenEntry()])
        raise OSError("synthetic scandir failure")

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)

    assert _iter_python_native_binary_candidates(runtime, site_packages) == []


def test_path_size_bytes_tolerates_scandir_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "tree"
    directory.mkdir()

    def fail_scandir(path: Path):
        if path == directory:
            raise OSError("synthetic scandir failure")
        return macos_app_bundle_module.os.scandir(path)

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fail_scandir)

    assert _path_size_bytes(directory) == 0


def test_path_size_bytes_tolerates_metadata_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = tmp_path / "broken"
    broken.write_text("unreadable metadata\n", encoding="utf-8")
    directory = tmp_path / "tree"
    directory.mkdir()
    retained = directory / "retained.txt"
    retained.write_text("kept\n", encoding="utf-8")
    skipped = directory / "skipped.txt"
    skipped.write_text("skipped\n", encoding="utf-8")
    original_is_symlink = Path.is_symlink
    original_scandir = macos_app_bundle_module.os.scandir

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self.entries = entries

        def __iter__(self):
            return iter(self.entries)

        def __enter__(self) -> "FakeScandir":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class FakeFileEntry:
        def __init__(self, path: Path, *, fail_stat: bool = False) -> None:
            self.path = str(path)
            self._path = path
            self._fail_stat = fail_stat

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            return False

        def stat(self, *, follow_symlinks: bool = True):
            if self._fail_stat:
                raise OSError("synthetic file metadata failure")
            return self._path.lstat()

    def fail_is_symlink(self: Path) -> bool:
        if self == broken:
            raise OSError("synthetic symlink metadata failure")
        return original_is_symlink(self)

    def fake_scandir(path: Path):
        if path == directory:
            return FakeScandir([FakeFileEntry(retained), FakeFileEntry(skipped, fail_stat=True)])
        return original_scandir(path)

    monkeypatch.setattr(Path, "is_symlink", fail_is_symlink)
    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)

    assert _path_size_bytes(broken) == 0
    assert _path_size_bytes(directory) == retained.lstat().st_size


def test_path_size_bytes_uses_scandir_without_os_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "tree"
    nested = directory / "nested"
    nested.mkdir(parents=True)
    retained = nested / "retained.txt"
    retained.write_text("kept\n", encoding="utf-8")
    symlink_target = tmp_path / "linked-target"
    symlink_target.mkdir()
    directory_link = directory / "linked"
    directory_link.symlink_to(symlink_target, target_is_directory=True)

    def fail_os_walk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_path_size_bytes should use os.scandir directly")

    monkeypatch.setattr(macos_app_bundle_module.os, "walk", fail_os_walk)

    assert _path_size_bytes(directory) == retained.lstat().st_size + directory_link.lstat().st_size


def test_path_size_bytes_tolerates_directory_symlink_metadata_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "tree"
    directory.mkdir()
    retained = directory / "retained.txt"
    retained.write_text("kept\n", encoding="utf-8")
    symlink_target = tmp_path / "linked-target"
    symlink_target.mkdir()
    broken_link = directory / "linked"
    broken_link.symlink_to(symlink_target, target_is_directory=True)
    original_scandir = macos_app_bundle_module.os.scandir

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self.entries = entries

        def __iter__(self):
            return iter(self.entries)

        def __enter__(self) -> "FakeScandir":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class FakeFileEntry:
        def __init__(self, path: Path, *, fail_stat: bool = False) -> None:
            self.path = str(path)
            self._path = path
            self._fail_stat = fail_stat

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            return False

        def stat(self, *, follow_symlinks: bool = True):
            if self._fail_stat:
                raise OSError("synthetic directory symlink metadata failure")
            return self._path.lstat()

    def fake_scandir(path: Path):
        if path == directory:
            return FakeScandir([FakeFileEntry(retained), FakeFileEntry(broken_link, fail_stat=True)])
        return original_scandir(path)

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)

    assert _path_size_bytes(directory) == retained.lstat().st_size


def test_prune_python_package_baggage_tolerates_directory_delete_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_packages = tmp_path / "site-packages"
    test_dir = site_packages / "nativepkg/tests"
    test_dir.mkdir(parents=True)
    (test_dir / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    original_rmtree = macos_app_bundle_module.shutil.rmtree

    def fail_rmtree(path: Path) -> None:
        if path == test_dir:
            raise OSError("synthetic package prune failure")
        original_rmtree(path)

    monkeypatch.setattr(macos_app_bundle_module.shutil, "rmtree", fail_rmtree)

    result = _prune_python_package_baggage(site_packages)

    assert result["directories_pruned"] == 0
    assert result["bytes_saved"] == 0
    assert test_dir.is_dir()


def test_prune_python_runtime_baggage_tolerates_directory_delete_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    include = runtime / "include"
    ensurepip = runtime / "lib/python3.12/ensurepip"
    include.mkdir(parents=True)
    ensurepip.mkdir(parents=True)
    (include / "Python.h").write_text("header\n", encoding="utf-8")
    (ensurepip / "__init__.py").write_text("ensurepip\n", encoding="utf-8")
    original_rmtree = macos_app_bundle_module.shutil.rmtree

    def fail_rmtree(path: Path) -> None:
        if path in {include, ensurepip}:
            raise OSError("synthetic runtime prune failure")
        original_rmtree(path)

    monkeypatch.setattr(macos_app_bundle_module.shutil, "rmtree", fail_rmtree)

    result = _prune_python_runtime_baggage(runtime)

    assert result["directories_pruned"] == 0
    assert result["bytes_saved"] == 0
    assert include.is_dir()
    assert ensurepip.is_dir()


def test_prune_python_runtime_baggage_tolerates_file_delete_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "python-runtime"
    runtime.mkdir()
    archive = runtime / "libpython3.12.a"
    archive.write_text("archive\n", encoding="utf-8")
    def fail_unlink(path: str) -> None:
        assert Path(path) == archive
        raise OSError("synthetic delete failure")

    monkeypatch.setattr(macos_app_bundle_module.os, "unlink", fail_unlink)

    result = _prune_python_runtime_baggage(runtime)

    assert result["files_pruned"] == 0
    assert result["bytes_saved"] >= archive.stat().st_size
    assert archive.is_file()


def test_strip_packaged_binaries_tolerates_resolve_and_stat_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResolveFailurePath:
        def is_symlink(self) -> bool:
            return False

        def is_file(self) -> bool:
            return True

        def resolve(self, strict: bool) -> Path:
            assert strict is True
            raise OSError("synthetic resolve failure")

    class StatBeforeFailurePath:
        def is_symlink(self) -> bool:
            return False

        def is_file(self) -> bool:
            return True

        def resolve(self, strict: bool) -> object:
            assert strict is True
            return self

        def stat(self) -> object:
            raise OSError("synthetic stat failure")

    class StatAfterFailurePath:
        def __init__(self) -> None:
            self.stat_calls = 0

        def __fspath__(self) -> str:
            return "/tmp/melix-stat-after-native.dylib"

        def is_symlink(self) -> bool:
            return False

        def is_file(self) -> bool:
            return True

        def resolve(self, strict: bool) -> object:
            assert strict is True
            return self

        def stat(self) -> object:
            self.stat_calls += 1
            if self.stat_calls == 1:
                return SimpleNamespace(st_size=128)
            raise OSError("synthetic stat-after-strip failure")

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/strip")

    stripped_commands: list[list[str]] = []

    def fake_strip(command: list[str], check: bool, **kwargs: object) -> None:
        assert check is True
        stripped_commands.append(command)

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_strip)

    result = _strip_packaged_binaries(
        [
            ResolveFailurePath(),  # type: ignore[list-item]
            StatBeforeFailurePath(),  # type: ignore[list-item]
            StatAfterFailurePath(),  # type: ignore[list-item]
        ]
    )

    assert result["attempted"] == 1
    assert result["stripped"] == 1
    assert result["failed"] == 0
    assert result["bytes_saved"] == 0
    assert stripped_commands == [["/usr/bin/strip", "-x", "/tmp/melix-stat-after-native.dylib"]]


def test_macho_detection_handles_non_files_and_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = tmp_path / "native.dylib"
    native.write_bytes(b"\xfe\xed\xfa\xcfpayload")
    plain = tmp_path / "plain.so"
    plain.write_text("plain text\n", encoding="utf-8")
    linked = tmp_path / "linked.so"
    linked.symlink_to(native)

    assert _is_macho_file(native) is True
    assert _is_macho_file(plain) is False
    assert _is_macho_file(linked) is False
    assert _is_macho_file(tmp_path / "missing.so") is False

    original_open = Path.open

    def fail_open(self: Path, *args: object, **kwargs: object):
        if self == native:
            raise OSError("synthetic read failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)
    assert _is_macho_file(native) is False


def test_ensure_sparkle_rpath_adds_and_verifies_loader_relative_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "melix-menubar"
    executable.write_bytes(b"macho")
    calls: list[list[str]] = []
    inspections = iter(("", "cmd LC_RPATH\npath @loader_path/../Frameworks\n"))

    monkeypatch.setattr(macos_app_bundle_module, "_is_macho_file", lambda path: True)
    monkeypatch.setattr(
        macos_app_bundle_module.shutil,
        "which",
        lambda name: f"/usr/bin/{name}",
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if command[0] == "/usr/bin/otool":
            return SimpleNamespace(stdout=next(inspections))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    assert _ensure_sparkle_executable_rpath(executable) is True
    assert calls == [
        ["/usr/bin/otool", "-l", str(executable)],
        [
            "/usr/bin/install_name_tool",
            "-add_rpath",
            "@loader_path/../Frameworks",
            str(executable),
        ],
        ["/usr/bin/otool", "-l", str(executable)],
    ]


def test_ensure_sparkle_rpath_skips_non_macho_and_reuses_existing_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "melix-menubar"
    executable.write_bytes(b"fixture")
    monkeypatch.setattr(macos_app_bundle_module, "_is_macho_file", lambda path: False)

    assert _ensure_sparkle_executable_rpath(executable) is False

    monkeypatch.setattr(macos_app_bundle_module, "_is_macho_file", lambda path: True)
    monkeypatch.setattr(
        macos_app_bundle_module.shutil,
        "which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            stdout="path @loader_path/../Frameworks\n"
        ),
    )

    assert _ensure_sparkle_executable_rpath(executable) is True


def test_read_sparkle_framework_version_requires_versioned_metadata(
    tmp_path: Path,
) -> None:
    framework = tmp_path / "Sparkle.framework"

    with pytest.raises(FileNotFoundError, match="Info.plist is missing"):
        _read_sparkle_framework_version(framework)

    resources = framework / "Versions/B/Resources"
    resources.mkdir(parents=True)
    (resources / "Info.plist").write_bytes(plistlib.dumps({}))

    with pytest.raises(ValueError, match="version is missing"):
        _read_sparkle_framework_version(framework)


def test_ensure_sparkle_rpath_requires_macos_linkage_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "melix-menubar"
    executable.write_bytes(b"macho")
    monkeypatch.setattr(macos_app_bundle_module, "_is_macho_file", lambda path: True)
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="otool and install_name_tool"):
        _ensure_sparkle_executable_rpath(executable)


def test_ensure_sparkle_rpath_fails_if_added_path_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "melix-menubar"
    executable.write_bytes(b"macho")
    monkeypatch.setattr(macos_app_bundle_module, "_is_macho_file", lambda path: True)
    monkeypatch.setattr(
        macos_app_bundle_module.shutil,
        "which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(stdout=""),
    )

    with pytest.raises(RuntimeError, match="missing @loader_path"):
        _ensure_sparkle_executable_rpath(executable)


def test_iter_nested_macho_signing_targets_uses_scandir_without_os_walk_or_path_rglob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "Melix.app"
    macos_dir = app_path / "Contents/MacOS"
    resources_dir = app_path / "Contents/Resources"
    nested_dir = resources_dir / "Nested.bundle/Contents/MacOS"
    macos_dir.mkdir(parents=True)
    nested_dir.mkdir(parents=True)

    launcher = macos_dir / "Melix"
    launcher.write_bytes(b"\xfe\xed\xfa\xcflauncher")
    helper = nested_dir / "Helper"
    helper.write_bytes(b"\xcf\xfa\xed\xfehelper")
    plain = resources_dir / "plain.txt"
    plain.write_text("not native\n", encoding="utf-8")

    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "ExternalHelper").write_bytes(b"\xfe\xed\xfa\xcfexternal")
    linked_dir = resources_dir / "Linked.bundle"
    linked_dir.symlink_to(external_dir, target_is_directory=True)

    def fail_rglob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError("_iter_nested_macho_signing_targets() should not allocate Path.rglob() trees")

    def fail_os_walk(*args: object, **kwargs: object):  # pragma: no cover - regression guard
        raise AssertionError("_iter_nested_macho_signing_targets() should use os.scandir() directly")

    def fail_sorted(iterable, *args: object, **kwargs: object):  # pragma: no cover - regression guard
        raise AssertionError("_iter_nested_macho_signing_targets() should stream unsorted scandir entries")

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    monkeypatch.setattr(macos_app_bundle_module.os, "walk", fail_os_walk)
    monkeypatch.setattr(macos_app_bundle_module, "sorted", fail_sorted, raising=False)

    assert _iter_nested_macho_signing_targets(app_path) == [
        launcher,
        helper,
    ]


def test_iter_nested_macho_signing_targets_tolerates_scandir_and_entry_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "Melix.app"
    app_path.mkdir()

    class BrokenEntry:
        name = "broken"
        path = str(app_path / "broken")

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            raise OSError("metadata disappeared")

    class MissingDirectoryEntry:
        name = "missing-dir"
        path = str(app_path / "missing-dir")

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            return True

    class FakeScandir:
        def __init__(self, entries: list[object]) -> None:
            self._entries = entries

        def __enter__(self) -> "FakeScandir":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def __iter__(self):
            return iter(self._entries)

    calls = 0

    def fake_scandir(path: Path) -> FakeScandir:
        nonlocal calls
        calls += 1
        if calls == 1:
            return FakeScandir([MissingDirectoryEntry(), BrokenEntry()])
        raise OSError(f"cannot scan {path}")

    monkeypatch.setattr(macos_app_bundle_module.os, "scandir", fake_scandir)

    assert _iter_nested_macho_signing_targets(app_path) == []


def test_copy_swiftpm_resource_bundles_restores_existing_bundle_on_copy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    source_bundle = source_root / "MelixMacOSMenubar_AppMain.bundle"
    source_bundle.mkdir(parents=True)
    (source_bundle / "fresh.txt").write_text("new", encoding="utf-8")
    target_root = tmp_path / "target"
    target_bundle = target_root / source_bundle.name
    target_bundle.mkdir(parents=True)
    (target_bundle / "existing.txt").write_text("old", encoding="utf-8")

    original_copytree = macos_app_bundle_module.shutil.copytree

    def fail_copytree(source: Path, target: Path, **kwargs: object) -> None:
        target.mkdir(parents=True)
        (target / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError(f"copy failed for {source}")

    monkeypatch.setattr(macos_app_bundle_module.shutil, "copytree", fail_copytree)

    with pytest.raises(OSError, match="copy failed"):
        _copy_swiftpm_resource_bundles(source_root, [target_root])

    assert (target_bundle / "existing.txt").read_text(encoding="utf-8") == "old"
    assert (target_bundle / "partial.txt").exists() is False
    assert (target_root / f"{target_bundle.name}.melix-backup").exists() is False

    monkeypatch.setattr(macos_app_bundle_module.shutil, "copytree", original_copytree)
    copied_paths = _copy_swiftpm_resource_bundles(source_root, [target_root])

    assert copied_paths == [target_bundle]
    assert (target_bundle / "fresh.txt").read_text(encoding="utf-8") == "new"
    assert (target_bundle / "existing.txt").exists() is False

    _exercise_launch_hardening_paths_for_resource_bundle_probe(tmp_path)


def _exercise_launch_hardening_paths_for_resource_bundle_probe(tmp_path: Path) -> None:
    def nested_tmp_path(name: str) -> Path:
        path = tmp_path / name
        path.mkdir(parents=True)
        return path

    test_build_macos_app_bundle_layout_uses_standard_app_structure(nested_tmp_path("layout"))
    test_render_native_launcher_source_execs_packaged_launcher_script()
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_write_unsigned_macos_app_bundle_writes_self_contained_layout(
            nested_tmp_path("self-contained"),
            scoped_monkeypatch,
        )
    test_copy_swiftpm_resource_bundles_does_not_copy_into_app_bundle_root(nested_tmp_path("contents-resources"))
    test_reject_external_python_framework_runtime_requires_python_binary(nested_tmp_path("missing-python"))

    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_adhoc_sign_macos_app_bundle_signs_and_verifies_app(
            scoped_monkeypatch,
            nested_tmp_path("sign"),
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_adhoc_sign_macos_app_bundle_skips_when_codesign_is_unavailable(
            scoped_monkeypatch,
            nested_tmp_path("no-codesign"),
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_adhoc_sign_macos_app_bundle_returns_false_when_codesign_fails(
            scoped_monkeypatch,
            nested_tmp_path("codesign-fails"),
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_reject_external_python_framework_runtime_blocks_framework_stub(
            nested_tmp_path("external-framework"),
            scoped_monkeypatch,
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_reject_external_python_framework_runtime_skips_when_otool_is_unavailable(
            nested_tmp_path("no-otool"),
            scoped_monkeypatch,
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_reject_external_python_framework_runtime_skips_when_otool_fails(
            nested_tmp_path("otool-fails"),
            scoped_monkeypatch,
        )


def test_copy_swiftpm_resource_bundles_does_not_copy_into_app_bundle_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_bundle = source_root / "MelixMacOSMenubar_AppMain.bundle"
    source_bundle.mkdir(parents=True)
    (source_bundle / "asset.txt").write_text("asset", encoding="utf-8")
    app_path = tmp_path / "Melix.app"
    contents_resources = app_path / "Contents/Resources"
    contents_resources.mkdir(parents=True)

    copied_paths = _copy_swiftpm_resource_bundles(source_root, [contents_resources])

    assert copied_paths == [contents_resources / source_bundle.name]
    assert (contents_resources / source_bundle.name / "asset.txt").is_file()
    assert (app_path / source_bundle.name).exists() is False


def test_adhoc_sign_macos_app_bundle_signs_and_verifies_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    native_extension = app_path / "Contents/Resources/python-site-packages/cv2/cv2.abi3.so"
    nested_dylib = app_path / "Contents/Resources/python-site-packages/cv2/.dylibs/libavcodec.61.dylib"
    non_native_data = app_path / "Contents/Resources/python-site-packages/cv2/data.so"
    for native_path in (native_extension, nested_dylib):
        native_path.parent.mkdir(parents=True, exist_ok=True)
        native_path.write_bytes(b"\xcf\xfa\xed\xfe" + b"mach-o")
    non_native_data.write_text("not a mach-o binary\n", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, target: "flags=0x10000(runtime)\n",
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, check, **kwargs: (calls.append(command) or SimpleNamespace(stdout="", stderr="")),
    )

    assert adhoc_sign_macos_app_bundle(app_path) is True
    sign_calls = [command for command in calls if "--sign" in command]
    signed_nested_targets = {Path(command[-1]) for command in sign_calls[:-1]}
    assert signed_nested_targets == {
        native_extension.resolve(),
        nested_dylib.resolve(),
    }
    assert non_native_data.resolve() not in signed_nested_targets
    assert sign_calls[-1][-1] == str(app_path.resolve())
    assert all("--options" in command and "runtime" in command for command in sign_calls)
    assert all("--deep" not in command for command in calls)


def test_sparkle_code_signing_plan_is_official_inside_out_order(tmp_path: Path) -> None:
    app = tmp_path / "Melix.app"
    framework = app / "Contents/Frameworks/Sparkle.framework"
    installer = framework / "Versions/B/XPCServices/Installer.xpc"
    downloader = framework / "Versions/B/XPCServices/Downloader.xpc"
    autoupdate = framework / "Versions/B/Autoupdate"
    updater = framework / "Versions/B/Updater.app"
    for directory in (installer, downloader, updater):
        directory.mkdir(parents=True, exist_ok=True)
    autoupdate.write_bytes(b"autoupdate")
    nested = app / "Contents/Resources/libworker.dylib"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"\xcf\xfa\xed\xfemach-o")

    plan = macos_code_signing_plan(app)

    assert [target.role for target in plan] == [
        "sparkle_installer_xpc",
        "sparkle_downloader_xpc",
        "sparkle_autoupdate",
        "sparkle_updater_app",
        "sparkle_framework",
        "nested_macho",
        "outer_app",
    ]
    assert [target.preserve_entitlements for target in plan[:5]] == [
        False,
        True,
        False,
        False,
        False,
    ]


def test_code_signing_plan_seals_computer_broker_helper_before_outer_app(
    tmp_path: Path,
) -> None:
    app = tmp_path / "Melix.app"
    helper = app / "Contents/Resources/MelixComputerUseBroker.app"
    broker = helper / "Contents/MacOS/melix-computer-broker"
    broker.parent.mkdir(parents=True)
    broker.write_bytes(b"\xcf\xfa\xed\xfe" + b"mach-o")
    (helper / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleExecutable": broker.name,
                "CFBundleIdentifier": "io.melix.menubar.computer-broker",
                "CFBundlePackageType": "APPL",
            }
        )
    )

    plan = macos_code_signing_plan(app)

    assert [target.role for target in plan] == [
        "nested_macho",
        "computer_broker_helper_app",
        "outer_app",
    ]
    assert plan[0].path == broker.resolve()
    assert plan[1].path == helper.resolve()
    assert plan[2].path == app.resolve()


def test_code_signing_plan_limits_library_validation_exception_to_dynamic_code_hosts(
    tmp_path: Path,
) -> None:
    app = tmp_path / "Melix.app"
    resources = app / "Contents/Resources"
    expected_hosts = {
        app / "Contents/MacOS/melix-menubar",
        resources / "melix-text-worker-swift",
        resources / "python-runtime/bin/python3.12",
    }
    ordinary_targets = {
        resources / "melix",
        resources / "melix-control-plane",
        resources / "python-site-packages/grpc/_cython/cygrpc.cpython-312-darwin.so",
    }
    for path in expected_hosts | ordinary_targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfe" + b"mach-o")

    plan = macos_code_signing_plan(app)

    exception_paths = {
        target.path
        for target in plan
        if target.disable_library_validation
    }
    assert exception_paths == {path.resolve() for path in expected_hosts}


def test_sparkle_code_signing_plan_rejects_missing_required_helper(tmp_path: Path) -> None:
    app = tmp_path / "Melix.app"
    framework = app / "Contents/Frameworks/Sparkle.framework"
    framework.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Sparkle code-signing target"):
        macos_code_signing_plan(app)


def test_codesign_entitlements_extract_complete_plist_from_either_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "Downloader.xpc"
    target.mkdir()
    payloads = iter(
        [
            SimpleNamespace(
                stdout=plistlib.dumps({"com.apple.security.network.client": True})
                + b"\nExecutable=/tmp/Downloader\n",
                stderr=b"codesign diagnostics\n",
            ),
            SimpleNamespace(
                stdout=(
                    b'<?xml version="1.0"?><plist version="1.0"><dict></plist>\n'
                    b"codesign diagnostics\n"
                ),
                stderr=b"warning before plist\n" + plistlib.dumps({}) + b"\nwarning after plist\n",
            ),
            SimpleNamespace(stdout=b'<?xml version="1.0"?><plist version="1.0">', stderr=b""),
            SimpleNamespace(stdout=plistlib.dumps([]), stderr=b""),
            SimpleNamespace(stdout=b"no entitlements", stderr=b""),
        ]
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda *args, **kwargs: next(payloads),
    )

    canonical = macos_app_bundle_module._canonical_codesign_entitlements(
        "/usr/bin/codesign", target
    )
    assert plistlib.loads(canonical) == {"com.apple.security.network.client": True}
    empty = macos_app_bundle_module._canonical_codesign_entitlements(
        "/usr/bin/codesign", target
    )
    assert plistlib.loads(empty) == {}
    with pytest.raises(RuntimeError, match="missing"):
        macos_app_bundle_module._canonical_codesign_entitlements("/usr/bin/codesign", target)
    with pytest.raises(RuntimeError, match="not a dictionary"):
        macos_app_bundle_module._canonical_codesign_entitlements("/usr/bin/codesign", target)
    with pytest.raises(RuntimeError, match="missing"):
        macos_app_bundle_module._canonical_codesign_entitlements("/usr/bin/codesign", target)


def test_locked_sparkle_downloader_empty_entitlements_are_preserved_but_autoupdate_is_not(
    tmp_path: Path,
) -> None:
    resolved = json.loads((REPO_ROOT / "apps/macos-menubar/Package.resolved").read_text())
    sparkle_pin = next(pin for pin in resolved["pins"] if pin["identity"] == "sparkle")
    assert sparkle_pin["state"]["version"] == "2.9.4"

    codesign = Path("/usr/bin/codesign")
    framework_source = (
        REPO_ROOT
        / "apps/macos-menubar/.build/artifacts/sparkle/Sparkle/Sparkle.xcframework"
        / "macos-arm64_x86_64/Sparkle.framework"
    )
    if not codesign.is_file() or not framework_source.is_dir():
        pytest.skip("locked Sparkle artifact is resolved only on the macOS package path")
    with (framework_source / "Versions/B/Resources/Info.plist").open("rb") as handle:
        framework_info = plistlib.load(handle)
    assert framework_info["CFBundleShortVersionString"] == "2.9.4"

    framework = tmp_path / "Melix.app/Contents/Frameworks/Sparkle.framework"
    framework.parent.mkdir(parents=True)
    framework.symlink_to(framework_source, target_is_directory=True)
    plan = macos_code_signing_plan(tmp_path / "Melix.app")
    downloader = next(target for target in plan if target.role == "sparkle_downloader_xpc")
    autoupdate = next(target for target in plan if target.role == "sparkle_autoupdate")

    assert downloader.preserve_entitlements is True
    assert autoupdate.preserve_entitlements is False
    canonical = macos_app_bundle_module._canonical_codesign_entitlements(
        str(codesign), downloader.path
    )
    assert plistlib.loads(canonical) == {}


def test_codesign_details_combines_standard_output_and_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "Melix.app"
    target.mkdir()
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="details", stderr="runtime"),
    )

    assert macos_app_bundle_module._codesign_details(
        "/usr/bin/codesign", target
    ) == "details\nruntime"


def test_codesign_identity_evidence_verifies_authority_requirement_and_both_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "Melix.app"
    target.mkdir()
    certificate = b"leaf-certificate"
    sha256 = hashlib.sha256(certificate).hexdigest()
    sha1 = hashlib.sha1(certificate).hexdigest()
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, path: "Authority=Melix GitHub Release Signing\nflags=runtime\n",
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if "-r-" in command:
            return SimpleNamespace(
                stdout="",
                stderr=f'designated => certificate root = H"{sha1}"',
            )
        prefix = Path(command[command.index("--extract-certificates") + 1])
        prefix.with_name(f"{prefix.name}0").write_bytes(certificate)
        return SimpleNamespace(stdout=b"", stderr=b"")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    macos_app_bundle_module._verify_codesign_identity_evidence(
        "/usr/bin/codesign",
        target,
        expected_certificate_sha256=sha256,
        expected_certificate_sha1=sha1,
        expected_authority="Melix GitHub Release Signing",
    )


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("authority", "authority"),
        ("requirement", "requirement"),
        ("sha256", "SHA-256"),
        ("sha1", "SHA-1"),
    ],
)
def test_codesign_identity_evidence_rejects_each_independent_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    message: str,
) -> None:
    target = tmp_path / "Melix.app"
    target.mkdir()
    certificate = b"leaf-certificate"
    sha256 = hashlib.sha256(certificate).hexdigest()
    sha1 = hashlib.sha1(certificate).hexdigest()
    authority = "Wrong" if failure == "authority" else "Melix GitHub Release Signing"
    expected_sha256 = "0" * 64 if failure == "sha256" else sha256
    expected_sha1 = "0" * 40 if failure == "sha1" else sha1
    requirement_sha1 = "0" * 40 if failure == "requirement" else expected_sha1
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, path: f"Authority={authority}\nflags=runtime\n",
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if "-r-" in command:
            return SimpleNamespace(
                stdout="",
                stderr=f'designated => certificate root = H"{requirement_sha1}"',
            )
        prefix = Path(command[command.index("--extract-certificates") + 1])
        prefix.with_name(f"{prefix.name}0").write_bytes(certificate)
        return SimpleNamespace(stdout=b"", stderr=b"")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=message):
        macos_app_bundle_module._verify_codesign_identity_evidence(
            "/usr/bin/codesign",
            target,
            expected_certificate_sha256=expected_sha256,
            expected_certificate_sha1=expected_sha1,
            expected_authority="Melix GitHub Release Signing",
        )


def test_sign_macos_app_bundle_uses_stable_identity_and_verifies_requirement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    native_binary = app_path / "Contents/MacOS/melix-menubar"
    native_binary.parent.mkdir(parents=True)
    native_binary.write_bytes(b"\xcf\xfa\xed\xfemach-o")
    keychain_path = tmp_path / "release-signing.keychain-db"
    keychain_path.write_bytes(b"fixture")
    certificate_sha1 = "0123456789abcdef0123456789abcdef01234567"
    calls: list[list[str]] = []
    verified_targets: list[Path] = []

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, target: "flags=0x10000(runtime)\n",
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_verify_codesign_identity_evidence",
        lambda codesign, target, **kwargs: verified_targets.append(target),
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_canonical_codesign_entitlements",
        lambda codesign, target: plistlib.dumps(
            {"com.apple.security.cs.disable-library-validation": True},
            fmt=plistlib.FMT_XML,
            sort_keys=True,
        ),
    )

    def fake_run(command: list[str], check: bool, **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    assert sign_macos_app_bundle(
        app_path,
        identity=certificate_sha1.upper(),
        keychain_path=keychain_path,
        expected_certificate_sha256="a" * 64,
        expected_certificate_sha1=certificate_sha1,
        expected_authority="Melix GitHub Release Signing",
    ) is True
    sign_calls = [command for command in calls if "--sign" in command]
    assert sign_calls[0][:-3] == [
        "/usr/bin/codesign",
        "--force",
        "--options",
        "runtime",
        "--sign",
        certificate_sha1.upper(),
        "--timestamp=none",
        "--keychain",
        str(keychain_path.resolve()),
    ]
    assert sign_calls[0][-3] == "--entitlements"
    assert Path(sign_calls[0][-2]).name == "disable-library-validation.plist"
    assert sign_calls[0][-1] == str(native_binary.resolve())
    assert sign_calls[1] == [
        "/usr/bin/codesign",
        "--force",
        "--options",
        "runtime",
        "--sign",
        certificate_sha1.upper(),
        "--timestamp=none",
        "--keychain",
        str(keychain_path.resolve()),
        str(app_path.resolve()),
    ]
    assert verified_targets == [native_binary.resolve(), app_path.resolve()]
    assert all("--deep" not in command for command in calls)


def test_sign_macos_app_bundle_preserves_required_helper_entitlements(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    helper = app_path / "Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices/Downloader.xpc"
    helper.mkdir(parents=True)
    target = macos_app_bundle_module.MacOSCodeSigningTarget(
        helper.resolve(), "sparkle_downloader_xpc", preserve_entitlements=True
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(macos_app_bundle_module, "macos_code_signing_plan", lambda app: [target])
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_canonical_codesign_entitlements",
        lambda codesign, path: b"canonical-entitlements",
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, path: "flags=0x10000(runtime)",
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, check, **kwargs: calls.append(command) or SimpleNamespace(),
    )

    assert sign_macos_app_bundle(app_path, identity="-") is True
    sign_call = next(command for command in calls if "--sign" in command)
    assert "--preserve-metadata=entitlements" in sign_call


def test_sign_macos_app_bundle_applies_and_verifies_library_validation_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    host = app_path / "Contents/MacOS/melix-menubar"
    host.parent.mkdir(parents=True)
    host.write_bytes(b"\xcf\xfa\xed\xfe" + b"mach-o")
    target = macos_app_bundle_module.MacOSCodeSigningTarget(
        host.resolve(),
        "nested_macho",
        disable_library_validation=True,
    )
    signed_entitlements: list[dict[str, object]] = []
    verified_entitlements: list[Path] = []
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(macos_app_bundle_module, "macos_code_signing_plan", lambda app: [target])
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, path: "flags=0x10000(runtime)",
    )

    def fake_entitlements(codesign: str, path: Path) -> bytes:
        verified_entitlements.append(path)
        return plistlib.dumps(
            {"com.apple.security.cs.disable-library-validation": True},
            fmt=plistlib.FMT_XML,
            sort_keys=True,
        )

    def fake_run(command: list[str], check: bool, **kwargs: object) -> SimpleNamespace:
        if "--sign" in command and "--entitlements" in command:
            entitlements_path = Path(command[command.index("--entitlements") + 1])
            signed_entitlements.append(plistlib.loads(entitlements_path.read_bytes()))
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(
        macos_app_bundle_module,
        "_canonical_codesign_entitlements",
        fake_entitlements,
    )
    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    assert sign_macos_app_bundle(app_path, identity="-") is True
    assert signed_entitlements == [
        {"com.apple.security.cs.disable-library-validation": True}
    ]
    assert verified_entitlements == [host.resolve()]


def test_sign_macos_app_bundle_rejects_conflicting_entitlement_policies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    target = macos_app_bundle_module.MacOSCodeSigningTarget(
        app_path / "Contents/Resources/conflicting-host",
        "nested_macho",
        preserve_entitlements=True,
        disable_library_validation=True,
    )
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(macos_app_bundle_module, "macos_code_signing_plan", lambda app: [target])

    assert sign_macos_app_bundle(app_path, identity="-") is False


@pytest.mark.parametrize("failure", ["runtime", "entitlements"])
def test_sign_macos_app_bundle_rejects_missing_runtime_or_changed_entitlements(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    app_path = tmp_path / "Melix.app"
    helper = app_path / "Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices/Downloader.xpc"
    helper.mkdir(parents=True)
    target = macos_app_bundle_module.MacOSCodeSigningTarget(
        helper.resolve(), "sparkle_downloader_xpc", preserve_entitlements=True
    )
    entitlement_values = iter([b"before", b"after" if failure == "entitlements" else b"before"])
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(macos_app_bundle_module, "macos_code_signing_plan", lambda app: [target])
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_canonical_codesign_entitlements",
        lambda codesign, path: next(entitlement_values),
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, path: "unsigned" if failure == "runtime" else "flags=runtime",
    )
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(),
    )

    assert sign_macos_app_bundle(app_path, identity="-") is False


@pytest.mark.parametrize(
    ("authority", "requirement", "expected"),
    [
        (
            "Different Signing Authority",
            'certificate root = H"0123456789abcdef0123456789abcdef01234567"',
            False,
        ),
        ("Melix GitHub Release Signing", "identifier io.melix.menubar", False),
    ],
)
def test_sign_macos_app_bundle_rejects_unstable_identity_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    authority: str,
    requirement: str,
    expected: bool,
) -> None:
    app_path = tmp_path / "Melix.app"
    app_path.mkdir()
    certificate_sha1 = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, target: "flags=0x10000(runtime)\n",
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_verify_codesign_identity_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("identity mismatch")),
    )

    def fake_run(command: list[str], check: bool, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    assert sign_macos_app_bundle(
        app_path,
        identity=certificate_sha1,
        expected_certificate_sha256="a" * 64,
        expected_certificate_sha1=certificate_sha1,
        expected_authority="Melix GitHub Release Signing",
    ) is expected


@pytest.mark.parametrize(
    "value",
    ["", "not-a-sha", "a" * 39, "g" * 40],
)
def test_normalize_codesign_certificate_sha1_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="40 hex digits"):
        normalize_codesign_certificate_sha1(value)


@pytest.mark.parametrize("value", ["", "not-a-sha", "a" * 63, "g" * 64])
def test_normalize_codesign_certificate_sha256_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="64 hex digits"):
        macos_app_bundle_module.normalize_codesign_certificate_sha256(value)


def test_sign_macos_app_bundle_requires_complete_identity_expectations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    app_path.mkdir()
    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")

    with pytest.raises(ValueError, match="must not be empty"):
        sign_macos_app_bundle(app_path, identity=" ")
    with pytest.raises(ValueError, match="must be provided together"):
        sign_macos_app_bundle(
            app_path,
            identity="-",
            expected_certificate_sha256="0" * 64,
            expected_certificate_sha1="0" * 40,
        )
    with pytest.raises(ValueError, match="authority must not be empty"):
        sign_macos_app_bundle(
            app_path,
            identity="0" * 40,
            expected_certificate_sha256="0" * 64,
            expected_certificate_sha1="0" * 40,
            expected_authority=" ",
        )
    with pytest.raises(ValueError, match="must match the expected certificate SHA-1"):
        sign_macos_app_bundle(
            app_path,
            identity="1" * 40,
            expected_certificate_sha256="0" * 64,
            expected_certificate_sha1="0" * 40,
            expected_authority="Melix GitHub Release Signing",
        )


def test_adhoc_sign_macos_app_bundle_skips_when_codesign_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    app_path.mkdir()

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, check: pytest.fail("codesign should not run when it is unavailable"),
    )

    assert adhoc_sign_macos_app_bundle(app_path) is False


def test_adhoc_sign_macos_app_bundle_returns_false_when_codesign_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "Melix.app"
    app_path.mkdir()

    def fail_codesign(command: list[str], check: bool) -> None:
        raise macos_app_bundle_module.subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
        )

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fail_codesign)

    assert adhoc_sign_macos_app_bundle(app_path) is False


def test_reject_external_python_framework_runtime_blocks_framework_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "python-runtime"
    (runtime_root / "bin").mkdir(parents=True)
    python_binary = runtime_root / "bin/python3"
    python_binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: object):
        assert command == ["otool", "-L", str(python_binary)]

        class Result:
            stdout = (
                f"{python_binary}:\n"
                "\t/Library/Frameworks/Python.framework/Versions/3.13/Python "
                "(compatibility version 3.13.0, current version 3.13.0)\n"
            )

        return Result()

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="external Python framework"):
        _reject_external_python_framework_runtime(runtime_root)


def test_reject_external_python_framework_runtime_requires_python_binary(tmp_path: Path) -> None:
    runtime_root = tmp_path / "python-runtime"
    runtime_root.mkdir()

    with pytest.raises(FileNotFoundError, match="Missing bundled Python executable"):
        _reject_external_python_framework_runtime(runtime_root)


def test_reject_external_python_framework_runtime_skips_when_otool_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "python-runtime"
    (runtime_root / "bin").mkdir(parents=True)
    python_binary = runtime_root / "bin/python3"
    python_binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: object):
        raise FileNotFoundError("otool")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    _reject_external_python_framework_runtime(runtime_root)


def test_reject_external_python_framework_runtime_skips_when_otool_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "python-runtime"
    (runtime_root / "bin").mkdir(parents=True)
    python_binary = runtime_root / "bin/python3"
    python_binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: object) -> None:
        raise macos_app_bundle_module.subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
        )

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    _reject_external_python_framework_runtime(runtime_root)


def test_copy_swiftpm_resource_bundles_uses_scandir_without_path_glob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    first_bundle = source_root / "A.bundle"
    second_bundle = source_root / "B.bundle"
    first_bundle.mkdir()
    second_bundle.mkdir()
    (first_bundle / "first.txt").write_text("first", encoding="utf-8")
    (second_bundle / "second.txt").write_text("second", encoding="utf-8")
    (source_root / "C.bundle").write_text("not a directory", encoding="utf-8")
    (source_root / "ignored.txt").write_text("ignored", encoding="utf-8")
    target_root = tmp_path / "target"
    target_root.mkdir()

    def fail_glob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError("_copy_swiftpm_resource_bundles() should not allocate Path.glob() results")

    monkeypatch.setattr(Path, "glob", fail_glob)

    copied_paths = _copy_swiftpm_resource_bundles(source_root, [target_root])

    assert copied_paths == [target_root / "A.bundle", target_root / "B.bundle"]
    assert (target_root / "A.bundle/first.txt").read_text(encoding="utf-8") == "first"
    assert (target_root / "B.bundle/second.txt").read_text(encoding="utf-8") == "second"
    assert (target_root / "C.bundle").exists() is False


def test_copy_swiftpm_resource_bundles_returns_empty_when_source_missing(tmp_path: Path) -> None:
    assert _copy_swiftpm_resource_bundles(tmp_path / "missing", [tmp_path / "target"]) == []


def test_write_unsigned_macos_app_bundle_requires_control_plane_executable(tmp_path: Path) -> None:
    menubar = tmp_path / "melix-menubar"
    cli = tmp_path / "melix"
    menubar.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    cli.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Missing Melix control-plane executable"):
        write_unsigned_macos_app_bundle(
            repo_root=tmp_path / "repo",
            executable_path=menubar,
            cli_executable_path=cli,
            control_plane_executable_path=tmp_path / "missing-melix-control-plane",
            swift_text_worker_executable_path=tmp_path / "melix-text-worker-swift",
            computer_broker_executable_path=tmp_path / "melix-computer-broker",
            swift_mlx_metallib_path=tmp_path / "mlx.metallib",
            swift_mlx_metallib_version="0.31.1",
            python_runtime_root=tmp_path / "python-runtime",
            python_site_packages_path=tmp_path / "python-site-packages",
            output_path=tmp_path / "Melix.app",
        )


def test_write_unsigned_macos_app_bundle_requires_computer_broker_executable(
    tmp_path: Path,
) -> None:
    executables = [
        tmp_path / name
        for name in (
            "melix-menubar",
            "melix",
            "melix-control-plane",
            "melix-text-worker-swift",
        )
    ]
    for executable in executables:
        executable.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Missing Computer Use broker executable"):
        write_unsigned_macos_app_bundle(
            repo_root=tmp_path / "repo",
            executable_path=executables[0],
            cli_executable_path=executables[1],
            control_plane_executable_path=executables[2],
            swift_text_worker_executable_path=executables[3],
            computer_broker_executable_path=tmp_path / "missing-melix-computer-broker",
            swift_mlx_metallib_path=tmp_path / "mlx.metallib",
            swift_mlx_metallib_version="0.31.1",
            python_runtime_root=tmp_path / "python-runtime",
            python_site_packages_path=tmp_path / "python-site-packages",
            output_path=tmp_path / "Melix.app",
        )


@pytest.mark.parametrize(
    ("metallib_exists", "metallib_version", "error_type", "message"),
    (
        (False, "0.31.1", FileNotFoundError, "Missing Swift MLX metallib"),
        (True, "   ", ValueError, "Swift MLX metallib version must not be empty"),
    ),
)
def test_write_unsigned_macos_app_bundle_validates_swift_mlx_metallib(
    tmp_path: Path,
    metallib_exists: bool,
    metallib_version: str,
    error_type: type[Exception],
    message: str,
) -> None:
    executables = [
        tmp_path / name
        for name in (
            "melix-menubar",
            "melix",
            "melix-control-plane",
            "melix-text-worker-swift",
            "melix-computer-broker",
        )
    ]
    for executable in executables:
        executable.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    metallib_path = tmp_path / "mlx.metallib"
    if metallib_exists:
        metallib_path.write_bytes(b"metal")

    with pytest.raises(error_type, match=message):
        write_unsigned_macos_app_bundle(
            repo_root=tmp_path / "repo",
            executable_path=executables[0],
            cli_executable_path=executables[1],
            control_plane_executable_path=executables[2],
            swift_text_worker_executable_path=executables[3],
            computer_broker_executable_path=executables[4],
            swift_mlx_metallib_path=metallib_path,
            swift_mlx_metallib_version=metallib_version,
            python_runtime_root=tmp_path / "python-runtime",
            python_site_packages_path=tmp_path / "python-site-packages",
            output_path=tmp_path / "Melix.app",
        )


def test_write_unsigned_macos_app_bundle_requires_an_icon_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "services/mlx-worker-python/worker").mkdir(parents=True)
    (repo_root / "packages/protocol/python").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "services/mlx-worker-python/worker/bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/worker/control_plane_bridge.py").write_text("print('bridge')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
    (repo_root / "packages/protocol/python/__init__.py").write_text("", encoding="utf-8")
    (repo_root / "scripts/wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")
    menubar = tmp_path / "melix-menubar"
    cli = tmp_path / "melix"
    control_plane = tmp_path / "melix-control-plane"
    swift_worker = tmp_path / "melix-text-worker-swift"
    computer_broker = tmp_path / "melix-computer-broker"
    for executable in (menubar, cli, control_plane, swift_worker, computer_broker):
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)
    python_site_packages = tmp_path / "python-site-packages"
    python_site_packages.mkdir()
    swift_mlx_metallib = tmp_path / "swift-mlx-runtime/mlx.metallib"
    swift_mlx_metallib.parent.mkdir()
    swift_mlx_metallib.write_bytes(b"matching-swift-mlx-metallib")

    try:
        write_unsigned_macos_app_bundle(
            repo_root=repo_root,
            executable_path=menubar,
            cli_executable_path=cli,
            control_plane_executable_path=control_plane,
            swift_text_worker_executable_path=swift_worker,
            computer_broker_executable_path=computer_broker,
            swift_mlx_metallib_path=swift_mlx_metallib,
            swift_mlx_metallib_version="0.31.1",
            python_runtime_root=python_runtime,
            python_site_packages_path=python_site_packages,
            output_path=tmp_path / "Melix.app",
            icon_source_path=tmp_path / "missing.icns",
        )
    except FileNotFoundError as error:
        assert "Missing macOS app icon" in str(error)
    else:
        raise AssertionError("expected write_unsigned_macos_app_bundle() to require an icon file")


def test_archive_macos_app_bundle_creates_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "Melix.app"
    (app_path / "Contents/MacOS").mkdir(parents=True)
    (app_path / "Contents/MacOS/Melix").write_text("echo\n", encoding="utf-8")
    archive_path = tmp_path / "Melix.zip"
    run_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        run_calls.append((command, {"check": check, **kwargs}))
        assert command[0] == "/usr/bin/ditto"
        Path(command[-1]).write_bytes(b"zip")

    monkeypatch.setattr(macos_app_bundle_module.subprocess, "run", fake_run)

    result = archive_macos_app_bundle(app_path, archive_path)

    assert result == archive_path
    assert archive_path.exists() is True
    assert run_calls[0][0] == [
        "/usr/bin/ditto",
        "-c",
        "-k",
        "--norsrc",
        "--keepParent",
        str(app_path.resolve()),
        str(archive_path.resolve()),
    ]
    assert run_calls[0][1]["check"] is True
    assert run_calls[0][1]["env"]["COPYFILE_DISABLE"] == "1"  # type: ignore[index]


def test_packaged_script_copy_rejects_ci_only_probe_scripts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_root = repo_root / "scripts"
    scripts_root.mkdir(parents=True)
    (scripts_root / "wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")
    (scripts_root / "synthetic_probe.py").write_text("print('probe')\n", encoding="utf-8")
    target_root = tmp_path / "target-scripts"
    target_root.mkdir()

    _copy_packaged_script(repo_root, target_root, "wait_for_worker_ready.py")

    assert (target_root / "wait_for_worker_ready.py").is_file()
    with pytest.raises(ValueError, match="CI-only probe script"):
        _copy_packaged_script(repo_root, target_root, "synthetic_probe.py")
    with pytest.raises(ValueError, match="CI-only probe script"):
        _copy_packaged_script(repo_root, target_root, "pr_scoped_performance_run.py")
