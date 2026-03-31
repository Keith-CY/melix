from __future__ import annotations

import plistlib
from pathlib import Path

from worker.productization.macos_app_bundle import (
    archive_macos_app_bundle,
    build_macos_app_bundle_layout,
    render_info_plist,
    render_launcher_script,
    render_portable_environment_script,
    resolve_python_runtime_root,
    write_unsigned_macos_app_bundle,
)


def test_build_macos_app_bundle_layout_uses_standard_app_structure(tmp_path: Path) -> None:
    layout = build_macos_app_bundle_layout(tmp_path / "Melix.app")

    assert layout.contents_path == layout.app_path / "Contents"
    assert layout.macos_path == layout.contents_path / "MacOS"
    assert layout.resources_path == layout.contents_path / "Resources"
    assert layout.launcher_path == layout.macos_path / "Melix"
    assert layout.bundled_swift_worker_binary_path == layout.resources_path / "melix-text-worker-swift"


def test_render_info_plist_marks_app_as_menu_bar_accessory() -> None:
    payload = plistlib.loads(
        render_info_plist(
            app_name="Melix",
            bundle_id="io.melix.menubar.preview",
            version="0.1.0",
        )
    )

    assert payload["CFBundleExecutable"] == "Melix"
    assert payload["CFBundleIdentifier"] == "io.melix.menubar.preview"
    assert payload["LSUIElement"] is True


def test_render_portable_environment_script_uses_home_relative_paths() -> None:
    script = render_portable_environment_script()

    assert 'export MELIX_APP_SUPPORT_DIR="$HOME/Library/Application Support/Melix"' in script
    assert 'export MELIX_RUNTIME_DIR="$MELIX_APP_SUPPORT_DIR/runtime"' in script


def test_render_launcher_script_starts_bundled_workers_and_app(tmp_path: Path) -> None:
    script = render_launcher_script(
        app_name="Melix",
        bundle_repo_root=Path("repo"),
        bundled_app_binary_name="melix-menubar",
        bundled_swift_worker_binary_name="melix-text-worker-swift",
        bundled_python_executable_relative_path="python-runtime/bin/python3",
        bundled_site_packages_relative_path="python-site-packages",
        wait_script_relative_path="repo/scripts/wait_for_worker_ready.py",
    )

    assert 'export MELIX_REPO_ROOT="$RESOURCES_DIR/repo"' in script
    assert 'export MELIX_PYTHON_BRIDGE_EXECUTABLE="$RESOURCES_DIR/python-runtime/bin/python3"' in script
    assert '"$RESOURCES_DIR/melix-text-worker-swift"' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" -m worker.bootstrap' in script
    assert '"$RESOURCES_DIR/python-runtime/bin/python3" "$RESOURCES_DIR/repo/scripts/wait_for_worker_ready.py"' in script
    assert '"$RESOURCES_DIR/melix-menubar" "$@"' in script


def test_resolve_python_runtime_root_resolves_from_python_executable(tmp_path: Path) -> None:
    runtime_root = tmp_path / "python-runtime"
    (runtime_root / "bin").mkdir(parents=True)
    executable = runtime_root / "bin/python3"
    executable.write_text("", encoding="utf-8")

    assert resolve_python_runtime_root(executable) == runtime_root


def test_write_unsigned_macos_app_bundle_writes_self_contained_layout(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "services/mlx-worker-python/worker").mkdir(parents=True)
    (repo_root / "packages/protocol/python").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "services/mlx-worker-python/worker/bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/worker/control_plane_bridge.py").write_text("print('bridge')\n", encoding="utf-8")
    (repo_root / "services/mlx-worker-python/pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
    (repo_root / "packages/protocol/python/__init__.py").write_text("", encoding="utf-8")
    (repo_root / "scripts/wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    menubar = tmp_path / "melix-menubar"
    swift_worker = tmp_path / "melix-text-worker-swift"
    for executable in (menubar, swift_worker):
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)

    python_runtime = tmp_path / "python-runtime"
    (python_runtime / "bin").mkdir(parents=True)
    python_executable = python_runtime / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)
    python_site_packages = tmp_path / "python-site-packages"
    python_site_packages.mkdir()
    (python_site_packages / "grpc.py").write_text("", encoding="utf-8")

    manifest = write_unsigned_macos_app_bundle(
        repo_root=repo_root,
        executable_path=menubar,
        swift_text_worker_executable_path=swift_worker,
        python_runtime_root=python_runtime,
        python_site_packages_path=python_site_packages,
        output_path=tmp_path / "Melix.app",
    )

    app_path = Path(manifest["app_path"])
    assert app_path.exists() is True
    assert Path(manifest["bundled_swift_worker_binary_path"]).exists() is True
    assert Path(manifest["bundled_python_runtime_path"]).exists() is True
    assert Path(manifest["bundled_site_packages_path"]).exists() is True
    assert Path(manifest["bundled_repo_root_path"]).joinpath("services/mlx-worker-python/worker/bootstrap.py").exists() is True
    launcher = Path(manifest["launcher_path"]).read_text(encoding="utf-8")
    assert "worker.bootstrap" in launcher
    assert "melix-text-worker-swift" in launcher
    plist_payload = plistlib.loads(Path(manifest["plist_path"]).read_bytes())
    assert plist_payload["CFBundleIdentifier"] == "io.melix.menubar.preview"


def test_archive_macos_app_bundle_creates_zip(tmp_path: Path) -> None:
    app_path = tmp_path / "Melix.app"
    (app_path / "Contents/MacOS").mkdir(parents=True)
    (app_path / "Contents/MacOS/Melix").write_text("echo\n", encoding="utf-8")
    archive_path = tmp_path / "Melix.zip"

    result = archive_macos_app_bundle(app_path, archive_path)

    assert result == archive_path
    assert archive_path.exists() is True
