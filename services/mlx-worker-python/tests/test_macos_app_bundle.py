from __future__ import annotations

import json
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import worker.productization.macos_app_bundle as macos_app_bundle_module

from worker.productization.macos_app_bundle import (
    _copy_swiftpm_resource_bundles,
    _reject_external_python_framework_runtime,
    _copy_packaged_script,
    _is_macho_file,
    _iter_nested_macho_signing_targets,
    _iter_python_native_binary_candidates,
    _path_size_bytes,
    _prune_python_package_baggage,
    _prune_python_runtime_baggage,
    _strip_packaged_binaries,
    adhoc_sign_macos_app_bundle,
    archive_macos_app_bundle,
    build_macos_app_bundle_layout,
    render_info_plist,
    render_launcher_script,
    render_native_launcher_source,
    render_portable_environment_script,
    resolve_python_runtime_root,
    resolve_site_packages_root,
    write_unsigned_macos_app_bundle,
)


def test_build_macos_app_bundle_layout_uses_standard_app_structure(tmp_path: Path) -> None:
    layout = build_macos_app_bundle_layout(tmp_path / "Melix.app")

    assert layout.contents_path == layout.app_path / "Contents"
    assert layout.macos_path == layout.contents_path / "MacOS"
    assert layout.resources_path == layout.contents_path / "Resources"
    assert layout.launcher_path == layout.macos_path / "Melix"
    assert layout.launcher_script_path == layout.resources_path / "Melix.sh"
    assert layout.bundled_swift_worker_binary_path == layout.resources_path / "melix-text-worker-swift"
    assert layout.bundled_icon_path == layout.resources_path / "MelixAppIcon.icns"


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
    assert "LSUIElement" not in payload


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
    assert 'export MELIX_BACKEND_MODE="auto"' in script
    assert 'export MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE="swift"' in script
    assert 'export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$MELIX_RUNTIME_DIR/python-bytecode-cache}"' in script


def test_render_launcher_script_starts_bundled_workers_and_app(tmp_path: Path) -> None:
    script = render_launcher_script(
        app_name="Melix",
        bundle_repo_root=Path("repo"),
        bundled_app_binary_name="melix-menubar",
        bundled_cli_binary_name="melix",
        bundled_swift_worker_binary_name="melix-text-worker-swift",
        bundled_python_executable_relative_path="python-runtime/bin/python3",
        bundled_site_packages_relative_path="python-site-packages",
        wait_script_relative_path="repo/scripts/wait_for_worker_ready.py",
    )

    assert 'export MELIX_REPO_ROOT="$RESOURCES_DIR/repo"' in script
    assert 'export MELIX_CLI="$RESOURCES_DIR/melix"' in script
    assert 'export MELIX_MENU_BAR_STARTUP_SURFACE="console"' in script
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in script
    assert 'export MELIX_PYTHON_BRIDGE_EXECUTABLE="$RESOURCES_DIR/python-runtime/bin/python3"' in script
    assert '"$RESOURCES_DIR/melix-text-worker-swift"' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" -m worker.bootstrap' in script
    assert '--backend-mode "$MELIX_BACKEND_MODE"' in script
    assert "export MELIX_SWIFT_WORKER_PID" in script
    assert "export MELIX_PYTHON_WORKER_PID" in script
    assert '"$MELIX_RUNTIME_DIR/python-bytecode-cache"' in script
    assert '"$MELIX_MODEL_OPS_JOBS_ROOT"' in script
    assert '"$MELIX_EVALUATION_JOBS_ROOT"' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" "$RESOURCES_DIR/repo/scripts/wait_for_worker_ready.py"' in script
    assert 'exec "$RESOURCES_DIR/melix-menubar" "$@"' in script
    assert "backend-mode deterministic" not in script


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
    swift_worker = tmp_path / "melix-text-worker-swift"
    for executable in (menubar, cli, swift_worker):
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)
    swiftpm_resource_bundle = tmp_path / "MelixMacOSMenubar_AppMain.bundle"
    swiftpm_resource_bundle.mkdir()
    (swiftpm_resource_bundle / "melix-status-template.png").write_bytes(b"png")

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)
    icon_file = tmp_path / "MelixAppIcon.icns"
    icon_file.write_bytes(b"icns")
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
        swift_text_worker_executable_path=swift_worker,
        python_runtime_root=python_runtime,
        python_site_packages_path=python_site_packages,
        output_path=tmp_path / "Melix.app",
        icon_source_path=icon_file,
        http_bind_host="0.0.0.0",
        http_port=12436,
    )

    app_path = Path(manifest["app_path"])
    assert app_path.exists() is True
    assert Path(manifest["bundled_cli_binary_path"]).exists() is True
    assert Path(manifest["bundled_swift_worker_binary_path"]).exists() is True
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
    assert (app_path / "MelixMacOSMenubar_AppMain.bundle").exists() is False
    assert (
        app_path / "Contents/Resources/MelixMacOSMenubar_AppMain.bundle/melix-status-template.png"
    ).is_file()
    assert manifest["bundled_swiftpm_resource_bundle_paths"] == [
        str(app_path / "Contents/Resources/MelixMacOSMenubar_AppMain.bundle"),
    ]
    assert Path(manifest["packaging_target_manifest_path"]).exists() is True
    assert Path(manifest["launcher_path"]).is_file() is True
    assert launcher_compile_calls == [
        (app_path / "Contents/MacOS/MelixLauncher.c", app_path / "Contents/MacOS/Melix"),
    ]
    launcher = Path(manifest["launcher_script_path"]).read_text(encoding="utf-8")
    assert "worker.bootstrap" in launcher
    assert 'export MELIX_CLI="$RESOURCES_DIR/melix"' in launcher
    assert "melix-text-worker-swift" in launcher
    assert 'export MELIX_MENU_BAR_STARTUP_SURFACE="console"' in launcher
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in launcher
    assert '"$MELIX_RUNTIME_DIR/python-bytecode-cache"' in launcher
    assert "export MELIX_SWIFT_WORKER_PID" in launcher
    assert "export MELIX_PYTHON_WORKER_PID" in launcher
    assert 'exec "$RESOURCES_DIR/melix-menubar" "$@"' in launcher
    plist_payload = plistlib.loads(Path(manifest["plist_path"]).read_bytes())
    assert plist_payload["CFBundleIdentifier"] == "io.melix.menubar.preview"
    assert plist_payload["CFBundleIconFile"] == "MelixAppIcon.icns"
    assert "LSUIElement" not in plist_payload
    env_script = Path(manifest["embedded_env_script_path"]).read_text(encoding="utf-8")
    assert 'export MELIX_PACKAGING_TARGET_ID="macos_app_bundle_preview"' in env_script
    assert 'export MELIX_PRODUCT_VERSION="0.1.0"' in env_script
    assert 'export MELIX_HTTP_HOST="${MELIX_HTTP_HOST:-0.0.0.0}"' in env_script
    assert 'export MELIX_HTTP_CONNECT_HOST="${MELIX_HTTP_CONNECT_HOST:-127.0.0.1}"' in env_script
    assert "MELIX_APP_SUPPORT_DIR" not in env_script
    assert 'export MELIX_MODEL_OPS_JOBS_ROOT="${MELIX_MODEL_OPS_JOBS_ROOT:-$MELIX_HOME/jobs/model-ops}"' in env_script
    assert 'export MELIX_EVALUATION_JOBS_ROOT="${MELIX_EVALUATION_JOBS_ROOT:-$MELIX_HOME/jobs/evaluation}"' in env_script
    target_payload = json.loads(Path(manifest["packaging_target_manifest_path"]).read_text(encoding="utf-8"))
    assert target_payload["packaging_target_id"] == "macos_app_bundle_preview"
    assert target_payload["logical_product_identity"] == "io.melix"
    assert target_payload["http_bind_host"] == "0.0.0.0"
    assert target_payload["http_connect_host"] == "127.0.0.1"
    assert target_payload["health_probe_url"] == "http://127.0.0.1:12436/health"
    assert manifest["service_base_url"] == "http://127.0.0.1:12436/v1"
    timings = manifest["timings"]
    for key in (
        "copy_app_binary_seconds",
        "copy_swift_worker_binary_seconds",
        "copy_icon_seconds",
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
    swift_worker = tmp_path / "melix-text-worker-swift"
    for executable in (menubar, cli, swift_worker):
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
        swift_text_worker_executable_path=swift_worker,
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
    assert "melix-text-worker-swift" in strip_calls
    assert "python3" in strip_calls
    assert "libpython3.12.dylib" in strip_calls
    assert "module.cpython-312-darwin.so" in strip_calls
    assert "linked-module.cpython-312-darwin.so" not in strip_calls
    assert external_native_extension.read_text(encoding="utf-8") == "external-native-debug-symbols\n"
    assert (native_package / "tests").is_dir()
    slimming = manifest["slimming"]
    assert slimming["swift_binaries_stripped"] == 3
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

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    monkeypatch.setattr(macos_app_bundle_module.os, "walk", fail_os_walk)

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
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, check: calls.append(command),
    )

    assert adhoc_sign_macos_app_bundle(app_path) is True
    signed_nested_targets = {Path(command[-1]) for command in calls[:-2]}
    assert signed_nested_targets == {
        native_extension.resolve(),
        nested_dylib.resolve(),
    }
    assert non_native_data.resolve() not in signed_nested_targets
    assert calls[-2:] == [
        [
            "/usr/bin/codesign",
            "--force",
            "--deep",
            "--sign",
            "-",
            str(app_path.resolve()),
        ],
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=4",
            str(app_path.resolve()),
        ],
    ]


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
    swift_worker = tmp_path / "melix-text-worker-swift"
    for executable in (menubar, cli, swift_worker):
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)
    python_site_packages = tmp_path / "python-site-packages"
    python_site_packages.mkdir()

    try:
        write_unsigned_macos_app_bundle(
            repo_root=repo_root,
            executable_path=menubar,
            cli_executable_path=cli,
            swift_text_worker_executable_path=swift_worker,
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
