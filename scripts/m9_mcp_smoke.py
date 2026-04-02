#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))

from tests.integration.helpers import LiveMelixStack, read_metrics_export


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    result = run_smoke(repo_root)

    print(json.dumps(result, indent=2, sort_keys=True))

    return 0 if result["passed"] else 1


def run_smoke(repo_root: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="melix-m9-mcp-") as tempdir:
        config_path = Path(tempdir) / "mcp-tools.json"
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
            metrics = wait_for_metric(stack.control_plane_metrics_path, "mcp.tool_injection_count")
            values = metrics["values"]
        finally:
            stack.stop()

    checks = {
        "config_load_latency_recorded": values["mcp.config_load_latency_ms"] >= 0,
        "disabled_source_count_recorded": values["mcp.disabled_tool_source_count"] == 1,
        "response_status_ok": response.status == 200,
        "stream_completed": "event: response.completed" in body,
        "tool_injection_recorded": values["mcp.tool_injection_count"] >= 1,
        "configured_tool_count_recorded": values["mcp.configured_tool_count"] == 2,
        "success_rate_recorded": values["mcp.tool_injection_success_rate"] == 1,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "config_path": str(config_path),
        "metrics": {
            "mcp.config_load_latency_ms": values["mcp.config_load_latency_ms"],
            "mcp.disabled_tool_source_count": values["mcp.disabled_tool_source_count"],
            "mcp.tool_injection_count": values["mcp.tool_injection_count"],
            "mcp.configured_tool_count": values["mcp.configured_tool_count"],
            "mcp.tool_injection_success_rate": values["mcp.tool_injection_success_rate"],
        },
    }


def wait_for_metric(metrics_path: Path, key: str, timeout_seconds: float = 10.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if metrics_path.exists():
            payload = read_metrics_export(metrics_path)
            values = payload.get("values", {})
            if isinstance(values, dict) and values.get(key, 0) >= 1:
                return payload
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for metric {key}")


if __name__ == "__main__":
    raise SystemExit(main())
