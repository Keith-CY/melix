from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "m8_admin_state_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m8_admin_state_smoke", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
m8_admin_state_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m8_admin_state_smoke)


def test_main_prints_json_payload(monkeypatch, capsys):
    payload = {
        "operator.session_restore_ms": 0.42,
        "operator.session_persist_write_ms": 1.86,
        "operator.session_tool_section_persisted": 1.0,
        "operator.session_tool_section_restored": 1.0,
        "operator.session_root_permissions_ok": 1.0,
        "operator.session_state_directory_permissions_ok": 1.0,
        "operator.session_file_permissions_ok": 1.0,
        "operator.offline_asset_external_reference_count": 0.0,
    }
    monkeypatch.setattr(m8_admin_state_smoke, "run_swift_smoke", lambda _: payload)
    monkeypatch.setattr(m8_admin_state_smoke.sys, "argv", ["m8_admin_state_smoke.py", "--json"])

    assert m8_admin_state_smoke.main() == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["ok"] is True
    assert emitted["metrics"] == payload
    assert emitted["persistence"]["restores_across_restart"] is True
    assert emitted["offline_assets"]["external_reference_count"] == 0.0


def test_main_prints_human_summary(monkeypatch, capsys):
    payload = {
        "operator.session_restore_ms": 0.42,
        "operator.session_persist_write_ms": 1.86,
        "operator.session_tool_section_persisted": 1.0,
        "operator.session_tool_section_restored": 1.0,
        "operator.session_root_permissions_ok": 1.0,
        "operator.session_state_directory_permissions_ok": 1.0,
        "operator.session_file_permissions_ok": 1.0,
        "operator.offline_asset_external_reference_count": 0.0,
    }
    monkeypatch.setattr(m8_admin_state_smoke, "run_swift_smoke", lambda _: payload)
    monkeypatch.setattr(m8_admin_state_smoke.sys, "argv", ["m8_admin_state_smoke.py"])

    assert m8_admin_state_smoke.main() == 0

    emitted = capsys.readouterr().out
    assert "M8.6 admin-state persistence smoke passed." in emitted
    assert '"operator.session_tool_section_restored": 1.0' in emitted


def test_run_swift_smoke_parses_metrics_from_stdout(monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    def fake_run(command, cwd, check, capture_output, text, env):
        recorded["command"] = command
        recorded["cwd"] = cwd
        recorded["check"] = check
        recorded["capture_output"] = capture_output
        recorded["text"] = text
        recorded["env"] = env
        return SimpleNamespace(
            stdout='M8_ADMIN_STATE_SMOKE={"operator.session_tool_section_restored":1}\n',
            stderr="",
        )

    monkeypatch.setattr(m8_admin_state_smoke.subprocess, "run", fake_run)

    payload = m8_admin_state_smoke.run_swift_smoke(tmp_path)

    assert payload == {"operator.session_tool_section_restored": 1}
    assert recorded["cwd"] == tmp_path
    assert recorded["check"] is True
    assert recorded["capture_output"] is True
    assert recorded["text"] is True
    assert "--disable-sandbox" in recorded["command"]
    assert recorded["command"][-1] == "OperatorSessionPersistenceSmokeTests"


def test_run_swift_smoke_parses_metrics_from_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(
        m8_admin_state_smoke.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="",
            stderr='warning\nM8_ADMIN_STATE_SMOKE={"operator.session_file_permissions_ok":1}\n',
        ),
    )

    payload = m8_admin_state_smoke.run_swift_smoke(tmp_path)

    assert payload == {"operator.session_file_permissions_ok": 1}


def test_run_swift_smoke_raises_when_metrics_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        m8_admin_state_smoke.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="no metrics", stderr=""),
    )

    try:
        m8_admin_state_smoke.run_swift_smoke(tmp_path)
    except RuntimeError as error:
        assert "M8_ADMIN_STATE_SMOKE" in str(error)
    else:
        raise AssertionError("expected missing metrics to raise RuntimeError")
