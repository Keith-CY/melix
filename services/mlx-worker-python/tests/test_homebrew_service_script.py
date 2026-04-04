from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "melix_homebrew_service.py"


def load_homebrew_service_module():
    assert MODULE_PATH.exists(), f"Expected Homebrew service entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_homebrew_service", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_module_prefers_environment_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    configured_root = REPO_ROOT / "infra"
    monkeypatch.setenv("MELIX_REPO_ROOT", str(configured_root))

    module = load_homebrew_service_module()

    assert module.CONFIGURED_REPO_ROOT == configured_root.resolve()


def test_manifest_command_emits_json_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_homebrew_service_module()
    seen: dict[str, object] = {}
    fake_layout = SimpleNamespace(service_instance_name="homebrew")
    fake_specs = [SimpleNamespace(label="io.melix.homebrew.control-plane")]

    def fake_build_homebrew_service_specs(**kwargs):
        seen["kwargs"] = kwargs
        return fake_layout, fake_specs

    def fake_ensure_runtime_directories(layout):
        seen["layout"] = layout

    def fake_build_homebrew_service_manifest(layout, specs):
        assert layout is fake_layout
        assert specs is fake_specs
        return {"services": [{"label": "io.melix.homebrew.control-plane"}]}

    monkeypatch.setattr(module, "build_homebrew_service_specs", fake_build_homebrew_service_specs)
    monkeypatch.setattr(module, "ensure_runtime_directories", fake_ensure_runtime_directories)
    monkeypatch.setattr(module, "build_homebrew_service_manifest", fake_build_homebrew_service_manifest)
    monkeypatch.setattr(module.sys, "argv", ["melix_homebrew_service.py", "manifest", "--json"])

    assert module.main() == 0
    assert seen["layout"] is fake_layout

    payload = json.loads(capsys.readouterr().out)
    assert payload["services"][0]["label"] == "io.melix.homebrew.control-plane"


def test_manifest_command_emits_json_payload_without_json_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_homebrew_service_module()

    monkeypatch.setattr(
        module,
        "build_homebrew_service_specs",
        lambda **kwargs: (SimpleNamespace(service_instance_name="homebrew"), []),
    )
    monkeypatch.setattr(module, "ensure_runtime_directories", lambda layout: None)
    monkeypatch.setattr(
        module,
        "build_homebrew_service_manifest",
        lambda layout, specs: {"services": [], "repo_root": os.fspath(REPO_ROOT)},
    )
    monkeypatch.setattr(module.sys, "argv", ["melix_homebrew_service.py", "manifest"])

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["repo_root"] == os.fspath(REPO_ROOT)


def test_run_command_invokes_service_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_homebrew_service_module()
    seen: dict[str, object] = {}
    fake_layout = SimpleNamespace(service_instance_name="homebrew")
    fake_specs = [SimpleNamespace(label="io.melix.homebrew.control-plane")]

    monkeypatch.setattr(
        module,
        "build_homebrew_service_specs",
        lambda **kwargs: (fake_layout, fake_specs),
    )
    monkeypatch.setattr(
        module,
        "ensure_runtime_directories",
        lambda layout: seen.setdefault("layout", layout),
    )
    monkeypatch.setattr(
        module,
        "build_homebrew_service_manifest",
        lambda layout, specs: {"services": [{"label": "io.melix.homebrew.control-plane"}]},
    )

    def fake_run_homebrew_service_bundle(specs):
        seen["specs"] = specs
        return 17

    monkeypatch.setattr(module, "run_homebrew_service_bundle", fake_run_homebrew_service_bundle)
    monkeypatch.setattr(module.sys, "argv", ["melix_homebrew_service.py", "run"])

    assert module.main() == 17
    assert seen["layout"] is fake_layout
    assert seen["specs"] is fake_specs
