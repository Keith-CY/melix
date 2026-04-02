from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pytest

from tests.integration.helpers import LiveMelixStack, read_metrics_export


def test_responses_endpoint_auto_injects_mcp_tools_from_repo_owned_config() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    runtime_root = repo_root / ".runtime" / "m9-mcp-tests"
    runtime_root.mkdir(parents=True, exist_ok=True)
    config_path = runtime_root / "mcp-tools.json"
    config_path.write_text(
        json.dumps(
            {
                "default_parser_mode": "json",
                "sources": [
                    {
                        "source_id": "filesystem",
                        "enabled": True,
                        "namespaces": ["tools.fs.read", "tools.fs.write"],
                    },
                    {
                        "source_id": "disabled-search",
                        "enabled": False,
                        "namespaces": ["tools.search"],
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_MCP_CONFIG_PATH": str(config_path)},
    )
    stack.start()

    try:
        response = urllib.request.urlopen(
            urllib.request.Request(
                stack.responses_url(),
                data=json.dumps(
                    {
                        "model": "melix-dev-text",
                        "stream": True,
                        "instructions": "Call tools when needed.",
                        "input": "hello responses",
                    }
                ).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )
        body = response.read().decode("utf-8")
        metrics = _wait_for_metric(stack.control_plane_metrics_path, "mcp.tool_injection_count")
        values = metrics["values"]

        assert response.status == 200
        assert "event: response.output_text.delta" in body
        assert values["mcp.config_load_latency_ms"] >= 0
        assert values["mcp.disabled_tool_source_count"] == 1
        assert values["mcp.tool_injection_count"] >= 1
        assert values["mcp.configured_tool_count"] == 2
        assert values["mcp.tool_injection_success_rate"] == 1
    finally:
        stack.stop()
        config_path.unlink(missing_ok=True)


def _wait_for_metric(metrics_path: Path, key: str, timeout_seconds: float = 10.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if metrics_path.exists():
            payload = read_metrics_export(metrics_path)
            values = payload.get("values", {})
            if isinstance(values, dict) and values.get(key, 0) >= 1:
                return payload
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for metric {key}")


def test_wait_for_metric_times_out_when_metric_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []

    monkeypatch.setattr(time, "time", lambda: next(values))
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(AssertionError, match="timed out waiting for metric missing"):
        _wait_for_metric(tmp_path / "missing-metrics.json", "missing", timeout_seconds=0.5)

    assert sleeps == [0.1]
