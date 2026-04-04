from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "install_local_product.py"


def load_install_local_product_module():
    assert MODULE_PATH.exists(), f"Expected install_local_product entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_install_local_product", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_forwards_service_instance_name_to_layout_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_install_local_product_module()
    seen: dict[str, object] = {}
    fake_layout = SimpleNamespace(
        launch_agents_dir=tmp_path / "LaunchAgents",
        install_manifest_path=tmp_path / "install-manifest.json",
        environment_script_path=tmp_path / "melix-env.sh",
    )

    def fake_build_local_product_layout(
        *,
        repo_root: str,
        home_dir: str,
        launch_agents_dir: str | None,
        http_port: int,
        service_instance_name: str,
        prefer_available_http_port: bool,
        product_version: str,
        update_channel_path: str | None,
    ):
        seen["repo_root"] = repo_root
        seen["home_dir"] = home_dir
        seen["launch_agents_dir"] = launch_agents_dir
        seen["http_port"] = http_port
        seen["service_instance_name"] = service_instance_name
        seen["prefer_available_http_port"] = prefer_available_http_port
        seen["product_version"] = product_version
        seen["update_channel_path"] = update_channel_path
        return fake_layout

    def fake_write_local_product_artifacts(
        layout,
        *,
        swift_backend_mode: str,
        python_backend_mode: str,
        dev_text_model_path: str,
    ):
        seen["layout"] = layout
        seen["swift_backend_mode"] = swift_backend_mode
        seen["python_backend_mode"] = python_backend_mode
        seen["dev_text_model_path"] = dev_text_model_path
        return {
            "bootstrap_commands": ["launchctl bootstrap gui/501 /tmp/io.melix.team-a.control-plane.plist"],
            "ready_probe_url": "http://127.0.0.1:18443/v1/models",
            "packaging_target_id": "launch_agents_checkout",
            "service_instance_name": "team-a",
        }

    monkeypatch.setattr(module, "build_local_product_layout", fake_build_local_product_layout)
    monkeypatch.setattr(module, "write_local_product_artifacts", fake_write_local_product_artifacts)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "install_local_product.py",
            "--repo-root",
            str(tmp_path / "repo"),
            "--home-dir",
            str(tmp_path / "home"),
            "--service-instance-name",
            "team-a",
            "--http-port",
            "18443",
            "--json",
        ],
    )

    assert module.main() == 0
    assert seen["service_instance_name"] == "team-a"
    assert seen["http_port"] == 18443
    assert seen["prefer_available_http_port"] is False
    assert seen["product_version"] == ""
    assert seen["update_channel_path"] is None
    assert seen["layout"] is fake_layout

    payload = json.loads(capsys.readouterr().out)
    assert payload["packaging_target_id"] == "launch_agents_checkout"
    assert payload["service_instance_name"] == "team-a"
    assert payload["ready_probe_url"] == "http://127.0.0.1:18443/v1/models"
