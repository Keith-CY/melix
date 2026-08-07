from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import pytest

from worker.runtime.agentic_tool_parking_budget import (
    AGENTIC_TOOL_PARKING_CONFIG_SCHEMA_VERSION,
    AGENTIC_TOOL_PARKING_DIAGNOSTIC_SCHEMA_VERSION,
    AGENTIC_TOOL_PARKING_EVENT_SCHEMA_VERSION,
    AGENTIC_TOOL_PARKING_STATE_SCHEMA_VERSION,
    AgenticToolApprovalParkingBudget,
    AgenticToolApprovalParkingConfig,
    AgenticToolApprovalParkingError,
    AgenticToolApprovalParkingEvent,
)


_Result = TypeVar("_Result")


def _config(
    *,
    total: int = 4,
    reserved: int = 2,
    parked: int = 100,
    tombstones: int = 1_000,
) -> AgenticToolApprovalParkingConfig:
    return AgenticToolApprovalParkingConfig(
        total_executor_capacity=total,
        reserved_executor_capacity=reserved,
        max_parked_approval_waits=parked,
        max_released_tombstones=tombstones,
    )


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


class _FakeExecutor:
    def __init__(self, budget: AgenticToolApprovalParkingBudget) -> None:
        self.budget = budget
        self.active_request_ids: set[str] = set()

    def begin(self, request_id: str) -> None:
        event = self.budget.begin_turn(request_id)
        assert event.outcome == "acquired"
        self.active_request_ids.add(request_id)

    def wait_for_approval(self, request_id: str) -> None:
        event = self.budget.park_for_approval(request_id)
        assert event.outcome == "parked"
        self.active_request_ids.remove(request_id)

    def resume(self, request_id: str) -> bool:
        event = self.budget.resume(request_id)
        if event.outcome == "resumed":
            self.active_request_ids.add(request_id)
            return True
        return False

    def release(self, request_id: str, *, reason: str) -> None:
        event = self.budget.release(request_id, reason=reason)
        assert event.outcome == "released"
        self.active_request_ids.discard(request_id)


def test_one_hundred_approval_waits_retain_two_executor_slots() -> None:
    budget = AgenticToolApprovalParkingBudget(
        config=_config(total=102, reserved=2)
    )

    def begin_and_park(
        index: int,
    ) -> tuple[AgenticToolApprovalParkingEvent, AgenticToolApprovalParkingEvent, int]:
        request_id = f"approval-{index:03d}"
        acquired = budget.begin_turn(request_id)
        parked = budget.park_for_approval(request_id)
        return (
            acquired,
            parked,
            int(budget.diagnostics()["executor_capacity_available"]),
        )

    results = _run_concurrently(100, begin_and_park)
    events = [event for acquired, parked, _ in results for event in (acquired, parked)]
    available_capacity = [available for _, _, available in results]
    diagnostics = budget.diagnostics()
    assert all(event.outcome in {"acquired", "parked"} for event in events)
    assert sorted(event.sequence for event in events) == list(range(1, 201))
    assert min(available_capacity) >= 2
    assert diagnostics["parked_request_count"] == 100
    assert diagnostics["parking_permits_used"] == 100
    assert diagnostics["executor_leases_used"] == 0
    assert diagnostics["executor_capacity_available"] == 102


def test_concurrent_resume_and_release_do_not_oversubscribe_or_leak() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    setup_events = []
    for index in range(100):
        request_id = f"approval-{index:03d}"
        setup_events.append(budget.begin_turn(request_id))
        setup_events.append(budget.park_for_approval(request_id))

    resumed = _run_concurrently(
        100, lambda index: budget.resume(f"approval-{index:03d}")
    )
    assert sum(event.outcome == "resumed" for event in resumed) == 2
    assert sum(event.outcome == "rejected" for event in resumed) == 98
    assert budget.diagnostics()["executor_capacity_available"] == 2

    reasons = ("completed", "cancelled", "timed_out", "runtime_reload")
    released = _run_concurrently(
        100,
        lambda index: budget.release(
            f"approval-{index:03d}", reason=reasons[index % len(reasons)]
        ),
    )
    suppressed = _run_concurrently(
        100,
        lambda index: budget.release(
            f"approval-{index:03d}", reason=reasons[index % len(reasons)]
        ),
    )
    diagnostics = budget.diagnostics()
    all_events = [*setup_events, *resumed, *released, *suppressed]

    assert all(event.outcome == "released" for event in released)
    assert all(event.outcome == "already_released" for event in suppressed)
    assert sorted(event.sequence for event in all_events) == list(range(1, 501))
    assert diagnostics["released_request_count"] == 100
    assert diagnostics["release_suppression_count"] == 100
    assert diagnostics["release_reason_counts"] == {
        "cancelled": 25,
        "completed": 25,
        "runtime_reload": 25,
        "timed_out": 25,
    }
    assert diagnostics["executor_leases_used"] == 0
    assert diagnostics["parking_permits_used"] == 0


def test_cancel_timeout_and_reload_release_each_resource_exactly_once() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    executor = _FakeExecutor(budget)
    executor.begin("cancel-executing")
    executor.begin("timeout-parked")
    executor.wait_for_approval("timeout-parked")
    executor.begin("reload-executing")
    executor.begin("reload-parked")
    executor.wait_for_approval("reload-parked")

    executor.release("cancel-executing", reason="cancelled")
    executor.release("timeout-parked", reason="timed_out")
    duplicate_cancel = budget.release("cancel-executing", reason="cancelled")

    restored = AgenticToolApprovalParkingBudget(
        config=_config(), state=budget.state_snapshot()
    )
    reload_events = restored.release_all_for_runtime_reload()
    duplicate_reload = restored.release("reload-parked", reason="runtime_reload")
    diagnostics = restored.diagnostics()

    assert duplicate_cancel.event_type == "release_suppressed"
    assert duplicate_cancel.outcome == "already_released"
    assert [event.request_id for event in reload_events] == [
        "reload-executing",
        "reload-parked",
    ]
    assert duplicate_reload.event_type == "release_suppressed"
    assert diagnostics["executor_leases_used"] == 0
    assert diagnostics["parking_permits_used"] == 0
    assert diagnostics["released_request_count"] == 4
    assert diagnostics["release_suppression_count"] == 2
    assert diagnostics["release_reason_counts"] == {
        "cancelled": 1,
        "completed": 0,
        "runtime_reload": 2,
        "timed_out": 1,
    }


def test_simultaneous_duplicate_release_has_one_winner() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    budget.begin_turn("same-request")

    events = _run_concurrently(
        2, lambda _: budget.release("same-request", reason="cancelled")
    )
    diagnostics = budget.diagnostics()

    assert sorted(event.outcome for event in events) == [
        "already_released",
        "released",
    ]
    assert len({event.sequence for event in events}) == 2
    assert diagnostics["released_request_count"] == 1
    assert diagnostics["release_suppression_count"] == 1
    assert diagnostics["executor_leases_used"] == 0


def test_released_tombstones_are_bounded_without_losing_cumulative_counts() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config(tombstones=3))
    reasons = ("completed", "cancelled", "timed_out", "runtime_reload")
    for index in range(10):
        request_id = f"bounded-{index}"
        budget.begin_turn(request_id)
        budget.release(request_id, reason=reasons[index % len(reasons)])

    snapshot = budget.state_snapshot()
    entries = snapshot["entries"]
    assert isinstance(entries, list)
    diagnostics = budget.diagnostics()
    assert [entry["request_id"] for entry in entries] == [
        "bounded-7",
        "bounded-8",
        "bounded-9",
    ]
    assert diagnostics["released_request_count"] == 10
    assert diagnostics["retained_released_tombstone_count"] == 3
    assert diagnostics["executor_lease_acquisition_count"] == 10
    assert diagnostics["release_reason_counts"] == {
        "cancelled": 3,
        "completed": 3,
        "runtime_reload": 2,
        "timed_out": 2,
    }

    retained = budget.release("bounded-9", reason="cancelled")
    evicted = budget.release("bounded-0", reason="cancelled")
    assert retained.outcome == "already_released"
    assert evicted.outcome == "unknown_request"

    restored = AgenticToolApprovalParkingBudget(
        config=_config(tombstones=3), state=budget.state_snapshot()
    )
    assert restored.diagnostics()["released_request_count"] == 10
    assert restored.begin_turn("bounded-0").outcome == "acquired"


def test_resume_reacquires_executor_before_returning_parking_permit() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    acquired = budget.begin_turn("resume-request")
    parked = budget.park_for_approval("resume-request")
    resumed = budget.resume("resume-request")

    diagnostics = budget.diagnostics()
    assert [acquired.event_type, parked.event_type, resumed.event_type] == [
        "executor_lease_acquired",
        "approval_wait_parked",
        "approval_wait_resumed",
    ]
    assert diagnostics["executor_leases_used"] == 1
    assert diagnostics["parking_permits_used"] == 0
    assert diagnostics["executor_lease_acquisition_count"] == 2
    assert diagnostics["approval_park_count"] == 1

    budget.release("resume-request", reason="completed")
    assert budget.diagnostics()["executor_leases_used"] == 0


def test_open_turn_without_approval_never_consumes_parking_capacity() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    executor = _FakeExecutor(budget)

    executor.begin("open-turn")
    executor.release("open-turn", reason="completed")

    diagnostics = budget.diagnostics()
    assert diagnostics["approval_park_count"] == 0
    assert diagnostics["parking_permits_used"] == 0
    assert diagnostics["capacity_rejection_count"] == 0
    assert diagnostics["release_reason_counts"]["completed"] == 1


def test_new_work_can_use_full_executor_capacity_but_resumes_preserve_reserve() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config(total=5, reserved=2))
    for index in range(5):
        assert budget.begin_turn(f"open-{index}").outcome == "acquired"

    rejected = budget.begin_turn("open-over-capacity")
    assert rejected.outcome == "rejected"
    assert rejected.failure_reason == "executor_capacity_exhausted"

    budget.release("open-0", reason="completed")
    budget.release("open-1", reason="completed")
    budget.release("open-2", reason="completed")
    budget.park_for_approval("open-3")
    resumed = budget.resume("open-3")

    assert resumed.outcome == "resumed"
    assert budget.diagnostics()["executor_capacity_available"] == 3


def test_parking_capacity_rejection_keeps_executor_lease() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config(parked=1))
    budget.begin_turn("parked")
    budget.park_for_approval("parked")
    budget.begin_turn("rejected")

    rejected = budget.park_for_approval("rejected")
    diagnostics = budget.diagnostics()

    assert rejected.outcome == "rejected"
    assert rejected.failure_reason == "approval_parking_capacity_exhausted"
    assert rejected.lifecycle_state == "executing"
    assert diagnostics["executor_leases_used"] == 1
    assert diagnostics["parking_permits_used"] == 1


def test_state_and_diagnostics_are_versioned_and_events_are_sanitized() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    secret = "request-secret-value"
    event = budget.begin_turn(secret)
    budget.park_for_approval(secret)

    state = budget.state_snapshot()
    diagnostics = budget.diagnostics()
    serialized_event = event.as_dict()

    assert budget.config.as_dict()["schema_version"] == (
        AGENTIC_TOOL_PARKING_CONFIG_SCHEMA_VERSION
    )
    assert state["schema_version"] == AGENTIC_TOOL_PARKING_STATE_SCHEMA_VERSION
    assert serialized_event["schema_version"] == AGENTIC_TOOL_PARKING_EVENT_SCHEMA_VERSION
    assert diagnostics["schema_version"] == (
        AGENTIC_TOOL_PARKING_DIAGNOSTIC_SCHEMA_VERSION
    )
    assert secret not in json.dumps(diagnostics, sort_keys=True)
    assert "arguments" not in json.dumps(serialized_event, sort_keys=True)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"total": 2}, "at least three"),
        ({"reserved": 1}, "At least two"),
        ({"total": 4, "reserved": 4}, "lower than total"),
        ({"parked": 0}, "positive"),
        ({"tombstones": 0}, "tombstone capacity"),
    ),
)
def test_config_rejects_unsafe_capacity(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(AgenticToolApprovalParkingError, match=message):
        _config(**kwargs)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda state: state.__setitem__("schema_version", "v2"), "schema version"),
        (
            lambda state: state.__setitem__("config_fingerprint", "0" * 64),
            "configured capacity",
        ),
        (lambda state: state.__setitem__("event_sequence", -1), "non-negative"),
        (lambda state: state.__setitem__("entries", {}), "must be a list"),
        (
            lambda state: state["entries"][0].__setitem__(  # type: ignore[index]
                "lifecycle_state", "unknown"
            ),
            "lifecycle state",
        ),
        (
            lambda state: state["entries"][0].__setitem__(  # type: ignore[index]
                "release_reason", "cancelled"
            ),
            "Active approval parking entries",
        ),
        (
            lambda state: state["entries"][0].__setitem__(  # type: ignore[index]
                "approval_park_count", 2
            ),
            "cannot exceed executor acquisitions",
        ),
    ),
)
def test_restore_rejects_invalid_or_mismatched_state(
    mutate: object, message: str
) -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    budget.begin_turn("restore-request")
    state = copy.deepcopy(budget.state_snapshot())
    mutate(state)  # type: ignore[operator]

    with pytest.raises(AgenticToolApprovalParkingError, match=message):
        AgenticToolApprovalParkingBudget(config=_config(), state=state)


def test_restore_rejects_duplicate_entries_and_capacity_overflow() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    budget.begin_turn("restore-request")
    duplicate = budget.state_snapshot()
    duplicate_entries = duplicate["entries"]
    assert isinstance(duplicate_entries, list)
    duplicate_entries.append(copy.deepcopy(duplicate_entries[0]))

    with pytest.raises(AgenticToolApprovalParkingError, match="unique"):
        AgenticToolApprovalParkingBudget(config=_config(), state=duplicate)

    overflow = AgenticToolApprovalParkingBudget(config=_config(total=5)).state_snapshot()
    template = {
        "lifecycle_state": "executing",
        "release_reason": "",
        "executor_lease_acquisition_count": 1,
        "approval_park_count": 0,
    }
    overflow["entries"] = [
        {"request_id": f"overflow-{index}", **template} for index in range(6)
    ]
    with pytest.raises(AgenticToolApprovalParkingError, match="executor capacity"):
        AgenticToolApprovalParkingBudget(config=_config(total=5), state=overflow)


def test_restore_rejects_inconsistent_tombstone_and_cumulative_counts() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    budget.begin_turn("released")
    budget.release("released", reason="completed")

    mismatched_order = budget.state_snapshot()
    mismatched_order["released_tombstone_order"] = []
    with pytest.raises(AgenticToolApprovalParkingError, match="must match"):
        AgenticToolApprovalParkingBudget(config=_config(), state=mismatched_order)

    mismatched_reasons = budget.state_snapshot()
    reason_counts = mismatched_reasons["release_reason_counts"]
    assert isinstance(reason_counts, dict)
    reason_counts["completed"] = 0
    with pytest.raises(AgenticToolApprovalParkingError, match="must equal"):
        AgenticToolApprovalParkingBudget(config=_config(), state=mismatched_reasons)

    low_cumulative_count = budget.state_snapshot()
    low_cumulative_count["executor_lease_acquisition_count"] = 0
    with pytest.raises(AgenticToolApprovalParkingError, match="acquisitions exceed"):
        AgenticToolApprovalParkingBudget(config=_config(), state=low_cumulative_count)

    low_park_count_budget = AgenticToolApprovalParkingBudget(config=_config())
    low_park_count_budget.begin_turn("parked")
    low_park_count_budget.park_for_approval("parked")
    low_park_count = low_park_count_budget.state_snapshot()
    low_park_count["approval_park_count"] = 0
    with pytest.raises(AgenticToolApprovalParkingError, match="parks exceed"):
        AgenticToolApprovalParkingBudget(config=_config(), state=low_park_count)


def test_restore_rejects_malformed_release_aggregates_and_tombstone_order() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())
    budget.begin_turn("released")
    budget.release("released", reason="completed")

    malformed_reasons = budget.state_snapshot()
    malformed_reasons["release_reason_counts"] = []
    with pytest.raises(AgenticToolApprovalParkingError, match="reason counts"):
        AgenticToolApprovalParkingBudget(config=_config(), state=malformed_reasons)

    malformed_order = budget.state_snapshot()
    malformed_order["released_tombstone_order"] = {}
    with pytest.raises(AgenticToolApprovalParkingError, match="must be a list"):
        AgenticToolApprovalParkingBudget(config=_config(), state=malformed_order)

    duplicate_order = budget.state_snapshot()
    duplicate_order["released_tombstone_order"] = ["released", "released"]
    with pytest.raises(AgenticToolApprovalParkingError, match="must be unique"):
        AgenticToolApprovalParkingBudget(config=_config(), state=duplicate_order)

    too_many_retained = budget.state_snapshot()
    too_many_retained["released_request_count"] = 0
    reason_counts = too_many_retained["release_reason_counts"]
    assert isinstance(reason_counts, dict)
    reason_counts["completed"] = 0
    with pytest.raises(AgenticToolApprovalParkingError, match="exceed released"):
        AgenticToolApprovalParkingBudget(config=_config(), state=too_many_retained)

    bounded = AgenticToolApprovalParkingBudget(config=_config(tombstones=1))
    for request_id in ("released-a", "released-b"):
        bounded.begin_turn(request_id)
        bounded.release(request_id, reason="completed")
    over_capacity = bounded.state_snapshot()
    entries = over_capacity["entries"]
    assert isinstance(entries, list)
    evicted_entry = copy.deepcopy(entries[0])
    evicted_entry["request_id"] = "released-a"
    entries.insert(0, evicted_entry)
    over_capacity["released_tombstone_order"] = ["released-a", "released-b"]
    with pytest.raises(AgenticToolApprovalParkingError, match="tombstone capacity"):
        AgenticToolApprovalParkingBudget(
            config=_config(tombstones=1), state=over_capacity
        )


def test_invalid_transitions_and_release_inputs_fail_closed() -> None:
    budget = AgenticToolApprovalParkingBudget(config=_config())

    with pytest.raises(AgenticToolApprovalParkingError, match="request id"):
        budget.begin_turn(" ")
    with pytest.raises(AgenticToolApprovalParkingError, match="has not acquired"):
        budget.park_for_approval("missing")

    budget.begin_turn("known")
    with pytest.raises(AgenticToolApprovalParkingError, match="cannot be reused"):
        budget.begin_turn("known")
    with pytest.raises(AgenticToolApprovalParkingError, match="lifecycle state"):
        budget.resume("known")
    with pytest.raises(AgenticToolApprovalParkingError, match="unsupported"):
        budget.release("known", reason="secret_reason")

    unknown = budget.release("never-started", reason="cancelled")
    assert unknown.event_type == "release_suppressed"
    assert unknown.outcome == "unknown_request"
