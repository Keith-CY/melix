from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest

import worker.productization.macos_app_bundle as macos_app_bundle_module

from worker.productization.macos_app_bundle import (
    _copy_swiftpm_resource_bundles,
    _reject_external_python_framework_runtime,
    _copy_packaged_script,
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


def test_write_unsigned_macos_app_bundle_writes_self_contained_layout(tmp_path: Path) -> None:
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
    launcher = Path(manifest["launcher_script_path"]).read_text(encoding="utf-8")
    assert "worker.bootstrap" in launcher
    assert 'export MELIX_CLI="$RESOURCES_DIR/melix"' in launcher
    assert "melix-text-worker-swift" in launcher
    assert 'export MELIX_MENU_BAR_STARTUP_SURFACE="console"' in launcher
    assert 'export MELIX_MENU_BAR_PRESENTATION_MODE="dock-and-tray"' in launcher
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
    test_write_unsigned_macos_app_bundle_writes_self_contained_layout(nested_tmp_path("self-contained"))
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
        test_reject_external_python_framework_runtime_blocks_framework_stub(
            nested_tmp_path("external-framework"),
            scoped_monkeypatch,
        )
    with pytest.MonkeyPatch.context() as scoped_monkeypatch:
        test_reject_external_python_framework_runtime_skips_when_otool_is_unavailable(
            nested_tmp_path("no-otool"),
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
    app_path.mkdir()
    calls: list[list[str]] = []

    monkeypatch.setattr(macos_app_bundle_module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        macos_app_bundle_module.subprocess,
        "run",
        lambda command, check: calls.append(command),
    )

    assert adhoc_sign_macos_app_bundle(app_path) is True
    assert calls == [
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


def test_archive_macos_app_bundle_creates_zip(tmp_path: Path) -> None:
    app_path = tmp_path / "Melix.app"
    (app_path / "Contents/MacOS").mkdir(parents=True)
    (app_path / "Contents/MacOS/Melix").write_text("echo\n", encoding="utf-8")
    archive_path = tmp_path / "Melix.zip"

    result = archive_macos_app_bundle(app_path, archive_path)

    assert result == archive_path
    assert archive_path.exists() is True


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
