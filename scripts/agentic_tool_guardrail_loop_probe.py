from __future__ import annotations

import json
import os
import statistics
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from worker.runtime.agentic_tool_guardrail_loop import (
    AgenticToolGuardrailConfig,
    AgenticToolGuardrailLoop,
)
from worker.runtime.agentic_tool_parking_budget import (
    AgenticToolApprovalParkingBudget,
    AgenticToolApprovalParkingConfig,
)

_PROBE_CONTRACT_VERSION = 1.0
_APPROVAL_WAIT_COUNT = 100
_Result = TypeVar("_Result")


def _acknowledge_probe_checkpoint(state: dict[str, object]) -> None:
    json.dumps(state, separators=(",", ":"))


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _timed_response(loop: AgenticToolGuardrailLoop, response: object) -> float:
    started = time.perf_counter()
    loop.handle_response(response)
    return (time.perf_counter() - started) * 1_000.0


def _run_concurrently(
    count: int, operation: Callable[[int], _Result]
) -> list[_Result]:
    barrier = threading.Barrier(count)

    def invoke(index: int) -> _Result:
        barrier.wait(timeout=10)
        return operation(index)

    with ThreadPoolExecutor(max_workers=count) as executor:
        futures = [executor.submit(invoke, index) for index in range(count)]
        return [future.result(timeout=20) for future in futures]


def _current_prompt_payload_metrics(
    loop: AgenticToolGuardrailLoop, turn: object
) -> tuple[int, int]:
    nudge = getattr(turn, "nudge")
    tool_results = getattr(turn, "tool_results")
    directive = loop.next_model_directive(nudge, tool_observations=tool_results)
    payload = {
        "tool_choice": directive.tool_choice,
        "context_messages": list(directive.context_messages),
        "tool_observations": list(directive.tool_observations),
    }
    return (
        len(json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        len(directive.tool_observations),
    )


def _prompt_and_ledger_metrics(*, prompt_turns: int) -> dict[str, float]:
    checkpoint_latencies: list[float] = []

    def acknowledge_checkpoint(state: dict[str, object]) -> None:
        started = time.perf_counter()
        json.dumps(state, separators=(",", ":"))
        checkpoint_latencies.append((time.perf_counter() - started) * 1_000.0)

    loop = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="probe-prompt-ledger",
            max_turns=prompt_turns + 1,
        ),
        persist_executing_state=acknowledge_checkpoint,
    )
    initial_state_bytes = len(
        json.dumps(loop.state_snapshot(), sort_keys=True, separators=(",", ":"))
    )
    prompt_payload_bytes: list[int] = []
    prompt_observation_counts: list[int] = []
    ledger_latencies: list[float] = []
    for index in range(prompt_turns):
        call = {
            "id": f"prompt-call-{index:06d}",
            "name": "local_compute",
            "arguments": {"code": "1 + 1"},
        }
        started = time.perf_counter()
        turn = loop.handle_response(call)
        transition_latency = (time.perf_counter() - started) * 1_000.0
        ledger_latencies.append(transition_latency - checkpoint_latencies[-1])
        payload_bytes, observation_count = _current_prompt_payload_metrics(loop, turn)
        prompt_payload_bytes.append(payload_bytes)
        prompt_observation_counts.append(observation_count)

    final_state = loop.state_snapshot()
    final_state_bytes = len(
        json.dumps(final_state, sort_keys=True, separators=(",", ":"))
    )
    halfway = prompt_turns // 2
    first_half_bytes = sum(prompt_payload_bytes[:halfway])
    second_half_bytes = sum(prompt_payload_bytes[halfway:])
    execution_ledger = final_state["execution_ledger"]
    if not isinstance(execution_ledger, dict):
        raise RuntimeError("guardrail execution ledger is not serializable")
    return {
        "prompt_current_window_growth_ratio_v1": (
            second_half_bytes / first_half_bytes
        ),
        "prompt_current_payload_bytes_max_v1": float(max(prompt_payload_bytes)),
        "prompt_current_observation_count_max_v1": float(
            max(prompt_observation_counts)
        ),
        "ledger_state_bytes_per_call_v1": (
            (final_state_bytes - initial_state_bytes) / prompt_turns
        ),
        "ledger_decision_latency_ms_mean_v1": statistics.fmean(ledger_latencies),
        "ledger_checkpoint_serialization_latency_ms_mean_v1": statistics.fmean(
            checkpoint_latencies
        ),
        "ledger_entry_count_v1": float(len(execution_ledger)),
    }


def _parking_metrics() -> dict[str, float]:
    wait_budget = AgenticToolApprovalParkingBudget(
        config=AgenticToolApprovalParkingConfig(
            total_executor_capacity=_APPROVAL_WAIT_COUNT + 2,
            reserved_executor_capacity=2,
            max_parked_approval_waits=_APPROVAL_WAIT_COUNT,
        )
    )
    initial_ledger_bytes = len(
        json.dumps(
            wait_budget.state_snapshot(), sort_keys=True, separators=(",", ":")
        )
    )

    def begin_and_park(index: int) -> tuple[float, int]:
        request_id = f"probe-approval-{index:03d}"
        started = time.perf_counter()
        acquired = wait_budget.begin_turn(request_id)
        parked = wait_budget.park_for_approval(request_id)
        latency = (time.perf_counter() - started) * 1_000.0
        if acquired.outcome != "acquired" or parked.outcome != "parked":
            raise RuntimeError("approval parking fixture unexpectedly rejected work")
        return (
            latency,
            int(wait_budget.diagnostics()["executor_capacity_available"]),
        )

    wait_results = _run_concurrently(_APPROVAL_WAIT_COUNT, begin_and_park)
    transition_latencies = [latency for latency, _ in wait_results]
    available_capacity = [available for _, available in wait_results]
    parked_ledger_bytes = len(
        json.dumps(
            wait_budget.state_snapshot(), sort_keys=True, separators=(",", ":")
        )
    )

    wait_releases = _run_concurrently(
        _APPROVAL_WAIT_COUNT,
        lambda index: wait_budget.release(
            f"probe-approval-{index:03d}", reason="completed"
        ),
    )
    if any(event.outcome != "released" for event in wait_releases):
        raise RuntimeError(  # pragma: no cover - defensive fixture invariant
            "concurrent approval wait cleanup was not exact once"
        )

    resume_budget = AgenticToolApprovalParkingBudget(
        config=AgenticToolApprovalParkingConfig(
            total_executor_capacity=4,
            reserved_executor_capacity=2,
            max_parked_approval_waits=_APPROVAL_WAIT_COUNT,
        )
    )
    for index in range(_APPROVAL_WAIT_COUNT):
        request_id = f"probe-resume-{index:03d}"
        resume_budget.begin_turn(request_id)
        resume_budget.park_for_approval(request_id)
    resume_events = _run_concurrently(
        _APPROVAL_WAIT_COUNT,
        lambda index: resume_budget.resume(f"probe-resume-{index:03d}"),
    )
    resumed_request_count = sum(
        event.outcome == "resumed" for event in resume_events
    )
    available_capacity.append(
        int(resume_budget.diagnostics()["executor_capacity_available"])
    )

    cleanup_events = _run_concurrently(
        66,
        lambda index: resume_budget.release(
            f"probe-resume-{index:03d}",
            reason="cancelled" if index < 33 else "timed_out",
        ),
    )
    if any(event.outcome != "released" for event in cleanup_events):
        raise RuntimeError(  # pragma: no cover - defensive fixture invariant
            "concurrent approval resume cleanup was not exact once"
        )
    restored = AgenticToolApprovalParkingBudget(
        config=resume_budget.config,
        state=resume_budget.state_snapshot(),
    )
    restored.release_all_for_runtime_reload()
    wait_diagnostics = wait_budget.diagnostics()
    resume_diagnostics = restored.diagnostics()
    return {
        "approval_wait_count_v1": float(_APPROVAL_WAIT_COUNT),
        "approval_resume_lease_count_v1": float(resumed_request_count),
        "concurrent_wait_ledger_bytes_per_request_v1": (
            (parked_ledger_bytes - initial_ledger_bytes) / _APPROVAL_WAIT_COUNT
        ),
        "executor_capacity_available_min_v1": float(min(available_capacity)),
        "parking_transition_latency_ms_mean_v1": statistics.fmean(
            transition_latencies
        ),
        "parking_transition_latency_ms_p95_v1": _percentile(
            transition_latencies, 0.95
        ),
        "executor_lease_leak_count_v1": float(
            int(wait_diagnostics["executor_leases_used"])
            + int(resume_diagnostics["executor_leases_used"])
        ),
        "parking_permit_leak_count_v1": float(
            int(wait_diagnostics["parking_permits_used"])
            + int(resume_diagnostics["parking_permits_used"])
        ),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_AGENTIC_GUARDRAIL_PROBE_ITERATIONS", "1000"))
    sample_count = int(os.environ.get("MELIX_AGENTIC_GUARDRAIL_PROBE_SAMPLES", "5"))
    if iterations < 1 or sample_count < 1:
        raise SystemExit("probe iterations and samples must be positive")
    prompt_turns = int(
        os.environ.get("MELIX_AGENTIC_GUARDRAIL_PROMPT_TURNS", "64")
    )
    if prompt_turns < 2 or prompt_turns % 2:
        raise SystemExit("probe prompt turns must be a positive even number")

    latency_samples: list[float] = []
    execution_counts: list[float] = []
    duplicate_counts: list[float] = []
    terminal_counts: list[float] = []
    leak_count = 0
    for sample_index in range(sample_count):
        sample_executions = 0
        sample_duplicates = 0
        sample_terminals = 0
        for iteration_index in range(iterations):
            loop = AgenticToolGuardrailLoop(
                config=AgenticToolGuardrailConfig(
                    request_id=f"probe-{sample_index}-{iteration_index}",
                    max_consecutive_malformed_responses=2,
                    max_consecutive_tool_failures=2,
                    max_turns=6,
                ),
                persist_executing_state=_acknowledge_probe_checkpoint,
            )
            call_id = f"call-{iteration_index}"
            secret = f"SENSITIVE_PROBE_VALUE_{sample_index}_{iteration_index}"
            call = {
                "id": call_id,
                "name": "local_compute",
                "arguments": {"code": "1 + 1", "probe_secret": secret},
            }
            collision = {
                "id": call_id,
                "name": "local_compute",
                "arguments": {"code": "2 + 2", "probe_secret": secret},
            }
            latency_samples.append(_timed_response(loop, None))
            latency_samples.append(_timed_response(loop, call))
            latency_samples.append(_timed_response(loop, call))
            latency_samples.append(_timed_response(loop, collision))
            diagnostics = loop.diagnostics()
            sample_executions += int(diagnostics["tool_execution_count"])
            sample_duplicates += int(diagnostics["duplicate_execution_count"])
            sample_terminals += int(diagnostics["terminal_failure_count"])
            leak_count += int(secret in json.dumps(diagnostics, sort_keys=True))
        execution_counts.append(sample_executions / iterations)
        duplicate_counts.append(sample_duplicates / iterations)
        terminal_counts.append(sample_terminals / iterations)

    metrics = {
        "guardrail_probe_contract_version": _PROBE_CONTRACT_VERSION,
        "guardrail_decision_latency_ms_mean": statistics.fmean(latency_samples),
        "guardrail_decision_latency_ms_p95": _percentile(latency_samples, 0.95),
        "tool_execution_count": statistics.fmean(execution_counts),
        "duplicate_execution_count": statistics.fmean(duplicate_counts),
        "terminal_failure_count": statistics.fmean(terminal_counts),
        "diagnostic_sensitive_value_leak_count": float(leak_count),
        "iteration_count": float(iterations),
        "sample_count": float(sample_count),
    }
    metrics.update(_prompt_and_ledger_metrics(prompt_turns=prompt_turns))
    metrics.update(_parking_metrics())
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
