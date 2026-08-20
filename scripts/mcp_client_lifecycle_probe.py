#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(
    os.environ.get(
        "MELIX_MCP_LIFECYCLE_PROBE_REPO_ROOT",
        Path(__file__).resolve().parents[1],
    )
).resolve()
FEATURE_AVAILABLE = (
    REPO_ROOT
    / "services/mlx-worker-python/worker/runtime/mcp_client.py"
).is_file()

if FEATURE_AVAILABLE:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

    from worker.runtime import mcp_client as mcp_client_module  # noqa: E402
    from worker.runtime.mcp_client import (  # noqa: E402
        MCPCancellationReceipt,
        MCPClientManager,
        MCPOwnerIdentity,
        MCPServerCapabilities,
        MCPSourceDefinition,
        MCPStdioTransport,
        MCPToolCatalog,
        MCPToolDefinition,
        MCPToolResult,
    )

    _has_source_lease = getattr(
        mcp_client_module,
        "_has_source_lease",
        lambda leases, source_id: any(key[0] == source_id for key in leases),
    )

    _TOOL = MCPToolDefinition(
        source_id="lifecycle-probe",
        name="echo",
        canonical_name="mcp__lifecycle-probe__echo",
        title="Echo",
        description="Deterministic lifecycle probe tool",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        annotations={},
        schema_digest="lifecycle-probe-schema-v1",
    )
else:
    _has_source_lease = None


class _DeterministicActor:
    """No-process actor used to isolate MCP manager lifecycle overhead."""

    def __init__(self, source: MCPSourceDefinition, *, environment: Any) -> None:
        del environment
        self.source = source
        self.live = True

    @property
    def is_live(self) -> bool:
        return self.live

    async def start(self) -> MCPServerCapabilities:
        return MCPServerCapabilities(
            source_id=self.source.source_id,
            transport_kind="stdio",
            protocol_version="probe-v1",
            server_name="deterministic-lifecycle-probe",
            server_version="1",
            capability_names=("tools",),
            tool_count=1,
            catalog_digest="lifecycle-probe-catalog-v1",
            connected_at_unix_ms=1,
        )

    async def list_tools(self, *, refresh: bool = False) -> MCPToolCatalog:
        del refresh
        return MCPToolCatalog(
            source_id=self.source.source_id,
            tools=(_TOOL,),
            catalog_digest="lifecycle-probe-catalog-v1",
            changed_since_initialize=False,
        )

    async def call_tool(self, **kwargs: Any) -> MCPToolResult:
        return MCPToolResult(
            source_id=self.source.source_id,
            tool_name=_TOOL.name,
            call_id=str(kwargs["call_id"]),
            content=(),
            structured_content={"ok": True},
            is_error=False,
            original_bytes=11,
            emitted_bytes=11,
            truncated=False,
            duration_ms=0.0,
            catalog_digest="lifecycle-probe-catalog-v1",
        )

    async def cancel(
        self,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
    ) -> MCPCancellationReceipt:
        del owner
        return MCPCancellationReceipt(
            source_id=self.source.source_id,
            run_id=run_id,
            call_id=call_id,
            disposition="accepted",
            side_effect_state="unknown",
            propagation_acknowledged=True,
        )

    async def cancel_owner(self, owner: MCPOwnerIdentity) -> None:
        del owner

    async def force_close(self) -> None:
        self.live = False


async def _sample(iterations: int) -> dict[str, float]:
    manager = MCPClientManager(environment={})
    source = MCPSourceDefinition(
        source_id="lifecycle-probe",
        transport=MCPStdioTransport(command="deterministic-no-process"),
    )
    owner = MCPOwnerIdentity(
        session_id="probe-session",
        branch_id="probe-branch",
        actor_id="probe-actor",
    )
    try:
        for _ in range(iterations):
            await manager.initialize(source, owner)
        for _ in range(iterations):
            await manager.list_tools(source.source_id, owner)
        for index in range(iterations):
            await manager.call_tool(
                source.source_id,
                owner=owner,
                run_id="probe-run",
                call_id=f"call-{index}",
                tool_name=_TOOL.name,
                arguments={},
                expected_schema_digest=_TOOL.schema_digest,
            )
        for index in range(iterations):
            await manager.cancel(
                source.source_id,
                owner,
                "probe-run",
                f"call-{index}",
            )

        snapshot_started = time.perf_counter()
        for _ in range(iterations):
            snapshot = manager.metrics_snapshot()
        snapshot_elapsed_ms = (
            time.perf_counter() - snapshot_started
        ) * 1_000

        if (
            snapshot.initialize.invocation_count != iterations
            or snapshot.list_tools.invocation_count != iterations
            or snapshot.call_tool.invocation_count != iterations
            or snapshot.cancel_propagation.invocation_count != iterations
        ):
            raise RuntimeError("MCP lifecycle metric counts changed")
        if snapshot.reconnect_count != 0 or snapshot.schema_change_count != 0:
            raise RuntimeError("deterministic MCP lifecycle probe drifted")
        return {
            "initialize_ms": snapshot.initialize.average_latency_ms,
            "list_tools_ms": snapshot.list_tools.average_latency_ms,
            "call_tool_ms": snapshot.call_tool.average_latency_ms,
            "cancel_propagation_ms": (
                snapshot.cancel_propagation.average_latency_ms
            ),
            "metrics_snapshot_ms": snapshot_elapsed_ms / iterations,
        }
    finally:
        await manager.close_all()


async def measure(iterations: int, sample_count: int) -> dict[str, float]:
    samples = [await _sample(iterations) for _ in range(sample_count)]
    lease_scan_samples = [_sample_source_lease_scan(iterations) for _ in range(sample_count)]
    return {
        "initialize_ms_mean": statistics.fmean(
            sample["initialize_ms"] for sample in samples
        ),
        "list_tools_ms_mean": statistics.fmean(
            sample["list_tools_ms"] for sample in samples
        ),
        "call_tool_ms_mean": statistics.fmean(
            sample["call_tool_ms"] for sample in samples
        ),
        "cancel_propagation_ms_mean": statistics.fmean(
            sample["cancel_propagation_ms"] for sample in samples
        ),
        "metrics_snapshot_ms_mean": statistics.fmean(
            sample["metrics_snapshot_ms"] for sample in samples
        ),
        "source_lease_scan_baseline_ms_mean": statistics.fmean(
            sample["baseline_ms"] for sample in lease_scan_samples
        ),
        "source_lease_scan_optimized_ms_mean": statistics.fmean(
            sample["optimized_ms"] for sample in lease_scan_samples
        ),
        "source_lease_scan_delta_ms": statistics.fmean(
            sample["optimized_ms"] - sample["baseline_ms"]
            for sample in lease_scan_samples
        ),
        "source_lease_scan_speedup": statistics.fmean(
            sample["baseline_ms"] / sample["optimized_ms"]
            for sample in lease_scan_samples
            if sample["optimized_ms"] > 0
        ),
        "operation_count": float(iterations),
        "sample_count": float(sample_count),
        "feature_available_count": 1.0,
    }


def _sample_source_lease_scan(iterations: int) -> dict[str, float]:
    if _has_source_lease is None:  # pragma: no cover - guarded by FEATURE_AVAILABLE.
        raise RuntimeError("source lease scan helper is unavailable")
    leases = {
        (f"source-{index % 16}", ("session", "branch", f"actor-{index}")): object()
        for index in range(256)
    }
    target_source_id = "source-15"

    baseline_started = time.perf_counter()
    baseline_hits = 0
    for _ in range(iterations):
        if any(key[0] == target_source_id for key in leases):
            baseline_hits += 1
    baseline_ms = (time.perf_counter() - baseline_started) * 1_000

    optimized_started = time.perf_counter()
    optimized_hits = 0
    for _ in range(iterations):
        if _has_source_lease(leases, target_source_id):
            optimized_hits += 1
    optimized_ms = (time.perf_counter() - optimized_started) * 1_000

    if baseline_hits != iterations or optimized_hits != iterations:  # pragma: no cover
        raise RuntimeError("source lease scan probe lost expected hits")
    return {"baseline_ms": baseline_ms, "optimized_ms": optimized_ms}


def main() -> int:
    iterations = int(
        os.environ.get("MELIX_MCP_LIFECYCLE_PROBE_ITERATIONS", "1000")
    )
    sample_count = int(
        os.environ.get("MELIX_MCP_LIFECYCLE_PROBE_SAMPLES", "5")
    )
    if iterations < 1 or sample_count < 1:
        raise ValueError("probe iteration and sample counts must be positive")
    if not FEATURE_AVAILABLE:
        print(
            json.dumps(
                {"feature_available_count": 0.0},
                sort_keys=True,
            )
        )
        return 0

    original_actor = mcp_client_module._MCPSourceActor
    mcp_client_module._MCPSourceActor = _DeterministicActor
    try:
        metrics = asyncio.run(measure(iterations, sample_count))
    finally:
        mcp_client_module._MCPSourceActor = original_actor
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
