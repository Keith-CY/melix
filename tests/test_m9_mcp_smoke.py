from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "m9_mcp_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m9_mcp_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m9_mcp_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m9_mcp_smoke)


def test_main_prints_smoke_result_without_json_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m9_mcp_smoke,
        "run_smoke",
        lambda repo_root: {
            "passed": True,
            "checks": {"response_status_ok": True},
            "config_path": str(repo_root / "mcp-tools.json"),
            "metrics": {"mcp.tool_injection_count": 1},
        },
    )
    monkeypatch.setattr(
        m9_mcp_smoke.sys,
        "argv",
        ["m9_mcp_smoke.py", "--repo-root", str(tmp_path)],
    )

    assert m9_mcp_smoke.main() == 0
    output = capsys.readouterr().out

    assert '"passed": true' in output
    assert '"mcp.tool_injection_count": 1' in output


def test_wait_for_metric_times_out_when_metric_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []

    monkeypatch.setattr(m9_mcp_smoke.time, "time", lambda: next(values))
    monkeypatch.setattr(m9_mcp_smoke.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(RuntimeError, match="timed out waiting for metric missing"):
        m9_mcp_smoke.wait_for_metric(tmp_path / "missing-metrics.json", "missing", timeout_seconds=0.5)

    assert sleeps == [0.1]
