from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "package_macos_menubar_app.py"


def load_package_macos_app_module():
    assert MODULE_PATH.exists(), f"Expected package_macos_menubar_app entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_package_macos_app", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_forwards_packaging_target_and_update_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    seen: dict[str, object] = {}

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        seen.update(kwargs)
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
        }

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--repo-root",
            str(tmp_path / "repo"),
            "--output-path",
            str(tmp_path / "Melix.app"),
            "--packaging-target-id",
            "macos_app_bundle_preview",
            "--update-channel-path",
            str(tmp_path / "stable.json"),
            "--icon-source-path",
            str(tmp_path / "MelixAppIcon.icns"),
            "--json",
        ],
    )

    assert module.main() == 0
    assert seen["packaging_target_id"] == "macos_app_bundle_preview"
    assert seen["update_channel_path"] == str(tmp_path / "stable.json")
    assert seen["icon_source_path"] == str(tmp_path / "MelixAppIcon.icns")

    payload = json.loads(capsys.readouterr().out)
    assert payload["packaging_target_id"] == "macos_app_bundle_preview"
