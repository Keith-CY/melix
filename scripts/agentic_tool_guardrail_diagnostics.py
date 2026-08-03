from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from pathlib import Path

from worker.runtime.agentic_tool_guardrail_loop import (
    AgenticToolGuardrailConfig,
    AgenticToolGuardrailRun,
    run_guarded_agentic_tool_loop,
)
from worker.runtime.agentic_tool_parking_budget import (
    AgenticToolApprovalParkingBudget,
    AgenticToolApprovalParkingConfig,
)
from worker.runtime.agentic_tools import (
    AgenticToolPrerequisite,
    DeterministicAgenticToolRuntime,
)

DIAGNOSTIC_BUNDLE_SCHEMA_VERSION = "melix.agentic_tool_guardrail_diagnostic_bundle.v1"


def _responder(responses: Iterable[object]) -> Callable[[object], object]:
    iterator = iter(responses)
    return lambda _directive: next(iterator)


def _fixture_runtime() -> DeterministicAgenticToolRuntime:
    return DeterministicAgenticToolRuntime(
        fixture_context={
            "text_corpus": {"default": []},
            "image_corpus": {"default": []},
        }
    )


def _prerequisite() -> AgenticToolPrerequisite:
    return AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )


def _run_evidence(scenario: str, run: AgenticToolGuardrailRun) -> dict[str, object]:
    return {
        "scenario": scenario,
        "outcome": run.outcome,
        "turn_actions": [turn.action for turn in run.turns],
        "events": [event.as_dict() for turn in run.turns for event in turn.events],
        "diagnostics": run.diagnostics,
    }


def _parking_evidence() -> dict[str, object]:
    wait_count = 100
    budget = AgenticToolApprovalParkingBudget(
        config=AgenticToolApprovalParkingConfig(
            total_executor_capacity=4,
            reserved_executor_capacity=2,
            max_parked_approval_waits=wait_count,
        )
    )
    events = []
    available_capacity: list[int] = []
    for index in range(wait_count):
        request_id = f"diagnostic-approval-{index:03d}"
        events.append(budget.begin_turn(request_id))
        events.append(budget.park_for_approval(request_id))
        available_capacity.append(
            int(budget.diagnostics()["executor_capacity_available"])
        )
    for index in range(3):
        event = budget.resume(f"diagnostic-approval-{index:03d}")
        events.append(event)
        if event.outcome == "resumed":
            available_capacity.append(
                int(budget.diagnostics()["executor_capacity_available"])
            )
    for index in range(33):
        events.append(
            budget.release(f"diagnostic-approval-{index:03d}", reason="cancelled")
        )
    for index in range(33, 66):
        events.append(
            budget.release(f"diagnostic-approval-{index:03d}", reason="timed_out")
        )

    restored = AgenticToolApprovalParkingBudget(
        config=budget.config,
        state=budget.state_snapshot(),
    )
    events.extend(restored.release_all_for_runtime_reload())
    events.append(
        restored.release("diagnostic-approval-099", reason="runtime_reload")
    )
    return {
        "scenario": "bounded_approval_parking_lifecycle",
        "approval_wait_count": wait_count,
        "executor_capacity_available_min": min(available_capacity),
        "events": [event.as_dict() for event in events],
        "diagnostics": restored.diagnostics(),
    }


def build_diagnostic_bundle() -> dict[str, object]:
    matching_query = "SENSITIVE_MATCHING_QUERY"
    success = run_guarded_agentic_tool_loop(
        _responder(
            (
                "I answered before completing the required tools.",
                {
                    "id": "text-1",
                    "name": "text_search",
                    "arguments": {"query": matching_query},
                },
                {
                    "id": "image-1",
                    "name": "image_search",
                    "arguments": {"query": matching_query},
                },
                "The guarded fixture completed.",
            )
        ),
        config=AgenticToolGuardrailConfig(
            request_id="diagnostic-success",
            required_tools=("text_search", "image_search"),
            prerequisites=(_prerequisite(),),
            max_consecutive_malformed_responses=2,
            max_consecutive_tool_failures=2,
            max_turns=6,
        ),
        runtime=_fixture_runtime(),
    )
    exhausted = run_guarded_agentic_tool_loop(
        _responder(
            (
                {
                    "id": "image-early-1",
                    "name": "image_search",
                    "arguments": {"query": "SENSITIVE_REJECTED_QUERY"},
                },
                {
                    "id": "image-early-2",
                    "name": "image_search",
                    "arguments": {"query": "SENSITIVE_REJECTED_QUERY"},
                },
            )
        ),
        config=AgenticToolGuardrailConfig(
            request_id="diagnostic-prerequisite-exhaustion",
            required_tools=("text_search", "image_search"),
            prerequisites=(_prerequisite(),),
            max_consecutive_malformed_responses=1,
            max_consecutive_tool_failures=2,
            max_turns=4,
        ),
        runtime=_fixture_runtime(),
    )
    return {
        "schema_version": DIAGNOSTIC_BUNDLE_SCHEMA_VERSION,
        "runs": [
            _run_evidence("healing_and_matching_prerequisite", success),
            _run_evidence("prerequisite_budget_exhaustion", exhausted),
        ],
        "parking": _parking_evidence(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write sanitized agent tool guardrail loop diagnostics."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".runtime/diagnostics/agent-tool-guardrail.json"),
        help="Destination JSON path.",
    )
    args = parser.parse_args(argv)
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_diagnostic_bundle(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
