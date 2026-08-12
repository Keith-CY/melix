from __future__ import annotations

from pathlib import Path

from worker.productization.macos_app_bundle import render_launcher_script
from worker.productization.packaging_targets import (
    packaged_python_import_isolation_env_exports,
    packaged_python_import_isolation_manifest,
)


def test_packaged_python_import_isolation_manifest_declares_required_flags() -> None:
    manifest = packaged_python_import_isolation_manifest()

    assert manifest["import_isolated"] is True
    assert manifest["pythonpath_policy"] == "bundled_site_packages_then_bundled_repo"
    assert manifest["env"] == {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
    }


def test_packaged_launcher_exports_import_isolation_before_pythonpath() -> None:
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

    pythonpath_index = script.index("export PYTHONPATH=")
    for export_line in packaged_python_import_isolation_env_exports():
        assert export_line in script
        assert script.index(export_line) < pythonpath_index
