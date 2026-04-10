from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module():
    module_path = REPO_ROOT / "scripts" / "m9_agent_export_smoke.py"
    module_spec = importlib.util.spec_from_file_location("m9_agent_export_smoke", module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_run_swift_smoke_uses_menubar_specific_swift_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    captured: dict[str, object] = {}

    class _Completed:
        stdout = 'M9_AGENT_EXPORT_METRICS={"integration.export_generation_ms":12.0,"integration.export_target_count":5.0}\n'
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_swift_smoke(tmp_path)

    assert payload["integration.export_generation_ms"] == 12.0
    assert captured["command"] == [
        "xcrun",
        "swift",
        "test",
        "--package-path",
        str(tmp_path / "apps" / "macos-menubar"),
        "--filter",
        "AgentIntegrationExportSmokeTests",
    ]
    assert captured["cwd"] == tmp_path
    env = captured["env"]
    assert env["HOME"] == str(tmp_path / ".swift-home" / "macos-menubar")
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        tmp_path / ".build" / "ModuleCache.noindex" / "macos-menubar"
    )


def test_main_supports_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "run_swift_smoke",
        lambda repo_root: {
            "integration.export_generation_ms": 12.0,
            "integration.export_target_count": 5.0,
        },
    )
    monkeypatch.setattr(module.sys, "argv", ["m9_agent_export_smoke.py", "--json"])

    assert module.main() == 0
    output = capsys.readouterr().out

    assert '"ok": true' in output
    assert '"integration.export_target_count": 5.0' in output


def test_run_swift_smoke_requires_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()

    class _Completed:
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: _Completed())

    with pytest.raises(RuntimeError, match="M9_AGENT_EXPORT_METRICS"):
        module.run_swift_smoke(tmp_path)
