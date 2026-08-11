#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import time


REPO_ROOT = Path(
    os.environ.get(
        "MELIX_AGENT_WORKER_PROBE_REPO_ROOT",
        Path(__file__).resolve().parents[1],
    )
).resolve()
FEATURE_AVAILABLE = all(
    path.is_file()
    for path in (
        REPO_ROOT
        / "services/mlx-worker-python/worker/runtime/computer_use_adapter.py",
        REPO_ROOT
        / "services/mlx-worker-python/worker/runtime/tool_execution_runtime.py",
    )
)

if FEATURE_AVAILABLE:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

    from worker.runtime.computer_use_adapter import (  # noqa: E402
        ComputerUseAdapterCancellationReceipt,
        ComputerUseToolDefinition,
    )
    from worker.runtime.mcp_client import MCPOwnerIdentity  # noqa: E402
    from worker.runtime.tool_execution_runtime import (  # noqa: E402
        ToolExecutionRuntime,
    )


class _DeterministicComputerCancellationAdapter:
    def __init__(self) -> None:
        self.definition = ComputerUseToolDefinition(
            source_id="computer-probe",
            adapter_kind="computer",
            name="computer_use_probe",
            title="Computer Use Probe",
            description="Deterministic cancellation-boundary probe",
            input_schema={
                "type": "object",
                "properties": {"operation": {"type": "string"}},
                "required": ["operation"],
                "additionalProperties": False,
            },
            schema_digest="computer-cancellation-probe-v1",
            risk_class="computer_control",
            replayability="evidence_only",
            annotations_untrusted=True,
        )
        self.cancellation_count = 0

    async def initialize(self) -> None:
        return None

    async def cancel(
        self,
        run_id: str,
        call_id: str,
    ) -> ComputerUseAdapterCancellationReceipt:
        if not run_id or not call_id:
            raise RuntimeError("probe cancellation identity is blank")
        self.cancellation_count += 1
        return ComputerUseAdapterCancellationReceipt(
            disposition="accepted",
            side_effect_committed=False,
        )

    async def close(self) -> None:
        return None


async def _sample(iterations: int) -> dict[str, float]:
    adapter = _DeterministicComputerCancellationAdapter()
    runtime = ToolExecutionRuntime(computer_use_adapter=adapter)
    owner = MCPOwnerIdentity(
        session_id="probe-session",
        branch_id="probe-branch",
        actor_id="probe-actor",
    )
    try:
        started = time.perf_counter()
        receipts = [
            await runtime.cancel_run(f"probe-run-{index}", owner)
            for index in range(iterations)
        ]
        first_elapsed_ms = (time.perf_counter() - started) * 1_000

        started = time.perf_counter()
        repeated = [
            await runtime.cancel_run(f"probe-run-{index}", owner)
            for index in range(iterations)
        ]
        repeated_elapsed_ms = (time.perf_counter() - started) * 1_000

        if not all(receipt.disposition == "accepted" for receipt in receipts):
            raise RuntimeError("first cancellation disposition changed")
        if not all(
            receipt.disposition == "already_terminal" for receipt in repeated
        ):
            raise RuntimeError("idempotent cancellation disposition changed")
        if adapter.cancellation_count != iterations:
            raise RuntimeError("adapter cancellation dispatch count changed")

        metrics = runtime.metrics_snapshot().worker_to_adapter_cancel
        if metrics.invocation_count != iterations or metrics.failure_count != 0:
            raise RuntimeError("worker cancellation metrics changed")
        return {
            "run_cancel_ms": first_elapsed_ms / iterations,
            "idempotent_cancel_ms": repeated_elapsed_ms / iterations,
            "worker_to_adapter_cancel_ms": (
                metrics.total_latency_ms / metrics.invocation_count
            ),
            "adapter_dispatch_count": float(adapter.cancellation_count),
        }
    finally:
        await runtime.close()


async def measure(iterations: int, sample_count: int) -> dict[str, float]:
    samples = [await _sample(iterations) for _ in range(sample_count)]
    return {
        "run_cancel_ms_mean": statistics.fmean(
            sample["run_cancel_ms"] for sample in samples
        ),
        "idempotent_cancel_ms_mean": statistics.fmean(
            sample["idempotent_cancel_ms"] for sample in samples
        ),
        "worker_to_adapter_cancel_ms_mean": statistics.fmean(
            sample["worker_to_adapter_cancel_ms"] for sample in samples
        ),
        "adapter_dispatch_count": statistics.fmean(
            sample["adapter_dispatch_count"] for sample in samples
        ),
        "iteration_count": float(iterations),
        "sample_count": float(sample_count),
        "feature_available_count": 1.0,
    }


def main() -> int:
    iterations = int(
        os.environ.get("MELIX_AGENT_CANCEL_PROBE_ITERATIONS", "500")
    )
    sample_count = int(
        os.environ.get("MELIX_AGENT_CANCEL_PROBE_SAMPLES", "5")
    )
    if iterations < 1 or iterations > 2_000 or sample_count < 1:
        raise ValueError("probe iteration and sample counts are out of bounds")
    if not FEATURE_AVAILABLE:
        print(
            json.dumps(
                {"feature_available_count": 0.0},
                sort_keys=True,
            )
        )
        return 0
    print(
        json.dumps(
            asyncio.run(measure(iterations, sample_count)),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
