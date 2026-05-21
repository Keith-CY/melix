#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import tool_registry as tool_registry_module  # noqa: E402
from worker.runtime.tool_registry import BUILTIN_AGENTIC_TOOL_NAMES, built_in_tool_registry  # noqa: E402


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    registry = built_in_tool_registry()
    expected_names = BUILTIN_AGENTIC_TOOL_NAMES
    elapsed_samples: list[float] = []
    descriptor_calls_samples: list[float] = []
    isolated_payload_samples: list[float] = []
    checksum = 0

    original_as_openai_tool = tool_registry_module.ToolDescriptor.as_openai_tool
    try:
        for _ in range(sample_count):
            call_count = 0

            def counting_as_openai_tool(self: tool_registry_module.ToolDescriptor) -> dict[str, object]:
                nonlocal call_count
                call_count += 1
                return original_as_openai_tool(self)

            tool_registry_module.ToolDescriptor.as_openai_tool = counting_as_openai_tool
            isolated_payload_count = 0
            started = time.perf_counter()
            for _index in range(iterations):
                tools = registry.as_openai_tools()
                names = tuple(tool["function"]["name"] for tool in tools)
                if names != expected_names:
                    raise RuntimeError(f"unexpected tool names: {names!r}")
                tools[0]["function"]["parameters"]["required"].append("mutated")
                if registry.as_openai_tools()[0]["function"]["parameters"]["required"] == [
                    "media_ref",
                    "region",
                ]:
                    isolated_payload_count += 1
                checksum += len(tools)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            descriptor_calls_samples.append(float(call_count))
            isolated_payload_samples.append(float(isolated_payload_count))
    finally:
        tool_registry_module.ToolDescriptor.as_openai_tool = original_as_openai_tool

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "descriptor_as_openai_tool_calls_mean": statistics.fmean(descriptor_calls_samples),
        "isolated_payload_calls_mean": statistics.fmean(isolated_payload_samples),
        "checksum": float(checksum),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_TOOL_REGISTRY_OPENAI_TOOLS_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_TOOL_REGISTRY_OPENAI_TOOLS_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
