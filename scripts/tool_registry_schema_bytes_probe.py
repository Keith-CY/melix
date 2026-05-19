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
from worker.runtime.tool_registry import (  # noqa: E402
    ToolDescriptor,
    built_in_tool_config,
    built_in_tool_registry,
)


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    registry = built_in_tool_registry()
    expected_schema_bytes = sum(len(tool.json_schema().encode("utf-8")) for tool in registry.tools)
    expected_required_arguments = [list(tool.required_arguments) for tool in registry.tools]
    original_json_schema = ToolDescriptor.json_schema
    elapsed_samples: list[float] = []
    schema_payload_elapsed_samples: list[float] = []
    json_schema_calls: list[float] = []
    schema_byte_count_calls: list[float] = []
    built_in_config_elapsed_samples: list[float] = []
    built_in_config_distinct_objects: list[float] = []
    checksum = 0
    original_schema_byte_count = getattr(ToolDescriptor, "schema_byte_count", None)

    try:
        for _ in range(sample_count):
            json_calls = 0
            byte_count_calls = 0

            def counted_json_schema(self: ToolDescriptor) -> str:
                nonlocal json_calls
                json_calls += 1
                return original_json_schema(self)

            def counted_schema_byte_count(self: ToolDescriptor) -> int:
                nonlocal byte_count_calls
                byte_count_calls += 1
                if original_schema_byte_count is None:
                    return len(original_json_schema(self).encode("utf-8"))
                return original_schema_byte_count(self)

            tool_registry_module.ToolDescriptor.json_schema = counted_json_schema
            tool_registry_module.ToolDescriptor.schema_byte_count = counted_schema_byte_count
            started = time.perf_counter()
            for _index in range(iterations):
                metrics = registry.metrics()
                if metrics.schema_bytes != expected_schema_bytes:
                    raise RuntimeError(
                        f"unexpected schema_bytes: {metrics.schema_bytes} != {expected_schema_bytes}"
                    )
                checksum += metrics.schema_bytes + metrics.required_argument_count
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            json_schema_calls.append(float(json_calls))
            schema_byte_count_calls.append(float(byte_count_calls))

            payload_started = time.perf_counter()
            for _index in range(iterations):
                for tool_index, tool in enumerate(registry.tools):
                    payload = tool.schema_payload()
                    if payload["required"] != expected_required_arguments[tool_index]:  # pragma: no cover
                        raise RuntimeError(
                            f"unexpected required arguments: {payload['required']!r}"
                        )
                    checksum += len(payload["required"])
            schema_payload_elapsed_samples.append((time.perf_counter() - payload_started) * 1000.0)

            first_config = built_in_tool_config()
            distinct_config_count = 0
            config_started = time.perf_counter()
            for _index in range(iterations):
                config = built_in_tool_config()
                if config is not first_config:
                    distinct_config_count += 1
                checksum += len(config.tools) + len(config.schema_version)
            built_in_config_elapsed_samples.append((time.perf_counter() - config_started) * 1000.0)
            built_in_config_distinct_objects.append(float(distinct_config_count))
    finally:
        tool_registry_module.ToolDescriptor.json_schema = original_json_schema
        if original_schema_byte_count is None:
            delattr(tool_registry_module.ToolDescriptor, "schema_byte_count")
        else:
            tool_registry_module.ToolDescriptor.schema_byte_count = original_schema_byte_count

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "schema_payload_elapsed_ms_mean": statistics.fmean(schema_payload_elapsed_samples),
        "json_schema_calls_mean": statistics.fmean(json_schema_calls),
        "schema_byte_count_calls_mean": statistics.fmean(schema_byte_count_calls),
        "built_in_tool_config_elapsed_ms_mean": statistics.fmean(
            built_in_config_elapsed_samples
        ),
        "built_in_tool_config_distinct_objects_mean": statistics.fmean(
            built_in_config_distinct_objects
        ),
        "schema_bytes": float(expected_schema_bytes),
        "checksum": float(checksum),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_TOOL_REGISTRY_METRICS_ITERATIONS", "40000"))
    sample_count = int(os.environ.get("MELIX_TOOL_REGISTRY_METRICS_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
