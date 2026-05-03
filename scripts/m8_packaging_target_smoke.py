#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.homebrew_service import build_homebrew_service_manifest, build_homebrew_service_specs
from worker.productization.install_assets import build_local_product_layout, write_local_product_artifacts
from worker.productization.macos_app_bundle import write_unsigned_macos_app_bundle
from worker.productization.packaging_targets import list_packaging_target_profiles


def _write_repo_fixture(repo_root: Path) -> None:
    (repo_root / "services/mlx-worker-python/worker").mkdir(parents=True, exist_ok=True)
    (repo_root / "packages/protocol/python").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    branding_dir = repo_root / "apps/macos-menubar/Sources/AppMain/Resources/Branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / "pyproject.toml").write_text(
        '[project]\nname = "melix"\nversion = "0.8.11"\n',
        encoding="utf-8",
    )
    (repo_root / "services/mlx-worker-python/worker/bootstrap.py").write_text(
        "print('bootstrap')\n",
        encoding="utf-8",
    )
    (repo_root / "services/mlx-worker-python/worker/control_plane_bridge.py").write_text(
        "print('bridge')\n",
        encoding="utf-8",
    )
    (repo_root / "services/mlx-worker-python/pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.8.11'\n",
        encoding="utf-8",
    )
    (repo_root / "packages/protocol/python/__init__.py").write_text("", encoding="utf-8")
    (repo_root / "scripts/wait_for_worker_ready.py").write_text("print('wait')\n", encoding="utf-8")
    (branding_dir / "MelixAppIcon.icns").write_bytes(b"melix-fixture-icon")


def _write_bundle_fixture(temp_root: Path) -> tuple[Path, Path, Path, Path, Path]:
    menubar_binary = temp_root / "melix-menubar"
    cli_binary = temp_root / "melix"
    swift_worker_binary = temp_root / "melix-text-worker-swift"
    for executable in (menubar_binary, cli_binary, swift_worker_binary):
        executable.write_text("#!/usr/bin/env bash\necho melix\n", encoding="utf-8")
        executable.chmod(0o755)

    python_runtime_root = temp_root / "python-runtime"
    (python_runtime_root / "bin").mkdir(parents=True, exist_ok=True)
    python_executable = python_runtime_root / "bin/python3"
    python_executable.write_text("#!/usr/bin/env bash\necho python\n", encoding="utf-8")
    python_executable.chmod(0o755)

    python_site_packages_path = temp_root / "python-site-packages"
    python_site_packages_path.mkdir(parents=True, exist_ok=True)
    (python_site_packages_path / "grpc.py").write_text("", encoding="utf-8")
    return menubar_binary, cli_binary, swift_worker_binary, python_runtime_root, python_site_packages_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="melix-packaging-target-") as temp_dir:
        temp_root = Path(temp_dir)
        repo_root = temp_root / "repo"
        repo_root.mkdir()
        _write_repo_fixture(repo_root)
        home_dir = temp_root / "home"
        home_dir.mkdir()

        layout = build_local_product_layout(
            repo_root=repo_root,
            home_dir=home_dir,
            launch_agents_dir=home_dir / "Library/LaunchAgents",
            http_port=18443,
        )
        launch_manifest = write_local_product_artifacts(layout)

        bin_dir = temp_root / "bin"
        bin_dir.mkdir()
        homebrew_layout, homebrew_specs = build_homebrew_service_specs(
            repo_root=repo_root,
            bin_dir=bin_dir,
            home_dir=home_dir,
            http_port=19443,
        )
        homebrew_manifest = build_homebrew_service_manifest(homebrew_layout, homebrew_specs)

        menubar_binary, cli_binary, swift_worker_binary, python_runtime_root, python_site_packages_path = (
            _write_bundle_fixture(temp_root)
        )
        bundle_manifest = write_unsigned_macos_app_bundle(
            repo_root=repo_root,
            executable_path=menubar_binary,
            cli_executable_path=cli_binary,
            swift_text_worker_executable_path=swift_worker_binary,
            python_runtime_root=python_runtime_root,
            python_site_packages_path=python_site_packages_path,
            output_path=temp_root / "Melix.app",
            version="0.8.11",
        )
        bundle_target_manifest = json.loads(
            Path(bundle_manifest["packaging_target_manifest_path"]).read_text(encoding="utf-8")
        )

    logical_identities = {
        launch_manifest["logical_product_identity"],
        homebrew_manifest["logical_product_identity"],
        bundle_target_manifest["logical_product_identity"],
    }
    packaging_kinds = {
        launch_manifest["packaging_kind"],
        homebrew_manifest["packaging_kind"],
        bundle_target_manifest["packaging_kind"],
    }
    payload = {
        "packaging_target_profile_count": len(list_packaging_target_profiles()),
        "packaging_target_shared_identity_ok": int(len(logical_identities) == 1),
        "packaging_target_distinct_packaging_kind_count": len(packaging_kinds),
        "packaging_target_launch_agents_profile_ok": int(
            launch_manifest["packaging_target_id"] == "launch_agents_checkout"
        ),
        "packaging_target_homebrew_profile_ok": int(
            homebrew_manifest["packaging_target_id"] == "homebrew_service"
        ),
        "packaging_target_app_bundle_profile_ok": int(
            bundle_target_manifest["packaging_target_id"] == "macos_app_bundle_preview"
        ),
        "packaging_target_smoke_ms": round((time.perf_counter() - started_at) * 1_000, 2),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
