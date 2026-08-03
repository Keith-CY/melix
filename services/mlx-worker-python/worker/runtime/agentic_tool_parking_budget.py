from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

AGENTIC_TOOL_PARKING_CONFIG_SCHEMA_VERSION = (
    "melix.agentic_tool_approval_parking_config.v1"
)
AGENTIC_TOOL_PARKING_STATE_SCHEMA_VERSION = (
    "melix.agentic_tool_approval_parking_state.v1"
)
AGENTIC_TOOL_PARKING_EVENT_SCHEMA_VERSION = (
    "melix.agentic_tool_approval_parking_event.v1"
)
AGENTIC_TOOL_PARKING_DIAGNOSTIC_SCHEMA_VERSION = (
    "melix.agentic_tool_approval_parking_diagnostic.v1"
)

_EXECUTING = "executing"
_PARKED = "parked_for_approval"
_RELEASED = "released"
_LIFECYCLE_STATES = frozenset({_EXECUTING, _PARKED, _RELEASED})
_RELEASE_REASONS = frozenset(
    {"completed", "cancelled", "timed_out", "runtime_reload"}
)
_STATE_COUNTER_FIELDS = (
    "capacity_rejection_count",
    "release_suppression_count",
    "event_sequence",
    "released_request_count",
    "executor_lease_acquisition_count",
    "approval_park_count",
)


class AgenticToolApprovalParkingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgenticToolApprovalParkingConfig:
    total_executor_capacity: int
    reserved_executor_capacity: int = 2
    max_parked_approval_waits: int = 100
    max_released_tombstones: int = 1_000

    def __post_init__(self) -> None:
        if self.total_executor_capacity < 3:
            raise AgenticToolApprovalParkingError(
                "Total executor capacity must be at least three."
            )
        if self.reserved_executor_capacity < 2:
            raise AgenticToolApprovalParkingError(
                "At least two executor slots must be reserved for new work."
            )
        if self.reserved_executor_capacity >= self.total_executor_capacity:
            raise AgenticToolApprovalParkingError(
                "Reserved executor capacity must be lower than total capacity."
            )
        if self.max_parked_approval_waits < 1:
            raise AgenticToolApprovalParkingError(
                "Approval parking capacity must be positive."
            )
        if self.max_released_tombstones < 1:
            raise AgenticToolApprovalParkingError(
                "Released approval tombstone capacity must be positive."
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": AGENTIC_TOOL_PARKING_CONFIG_SCHEMA_VERSION,
            "total_executor_capacity": self.total_executor_capacity,
            "reserved_executor_capacity": self.reserved_executor_capacity,
            "max_parked_approval_waits": self.max_parked_approval_waits,
            "max_released_tombstones": self.max_released_tombstones,
        }


@dataclass(frozen=True, slots=True)
class AgenticToolApprovalParkingEvent:
    sequence: int
    event_type: str
    outcome: str
    request_id: str
    lifecycle_state: str
    release_reason: str = ""
    failure_reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": AGENTIC_TOOL_PARKING_EVENT_SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "outcome": self.outcome,
            "request_id": self.request_id,
            "lifecycle_state": self.lifecycle_state,
            "release_reason": self.release_reason,
            "failure_reason": self.failure_reason,
        }


class AgenticToolApprovalParkingBudget:
    """Process-wide executor and approval-wait lifecycle ledger.

    Parked requests hold a bounded parking permit and no executor lease. Resumes
    may consume only capacity above the configured reserve, leaving executor
    slots available for new, non-approval work.
    """

    def __init__(
        self,
        *,
        config: AgenticToolApprovalParkingConfig,
        state: Mapping[str, object] | None = None,
    ) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._state = self._restore_state(state)

    def begin_turn(self, request_id: str) -> AgenticToolApprovalParkingEvent:
        with self._lock:
            return self._begin_turn(request_id)

    def _begin_turn(self, request_id: str) -> AgenticToolApprovalParkingEvent:
        request_id = self._request_id(request_id)
        if request_id in self._entries():
            raise AgenticToolApprovalParkingError(
                "Approval parking request ids cannot be reused."
            )
        if self._executor_leases_used() >= self.config.total_executor_capacity:
            return self._capacity_rejected(
                request_id=request_id,
                lifecycle_state="not_started",
                failure_reason="executor_capacity_exhausted",
            )
        self._entries()[request_id] = {
            "lifecycle_state": _EXECUTING,
            "release_reason": "",
            "executor_lease_acquisition_count": 1,
            "approval_park_count": 0,
        }
        self._state["executor_lease_acquisition_count"] = (
            int(self._state["executor_lease_acquisition_count"]) + 1
        )
        return self._event(
            event_type="executor_lease_acquired",
            outcome="acquired",
            request_id=request_id,
            lifecycle_state=_EXECUTING,
        )

    def park_for_approval(
        self, request_id: str
    ) -> AgenticToolApprovalParkingEvent:
        with self._lock:
            return self._park_for_approval(request_id)

    def _park_for_approval(
        self, request_id: str
    ) -> AgenticToolApprovalParkingEvent:
        request_id, entry = self._active_entry(request_id, expected_state=_EXECUTING)
        if self._parking_permits_used() >= self.config.max_parked_approval_waits:
            return self._capacity_rejected(
                request_id=request_id,
                lifecycle_state=_EXECUTING,
                failure_reason="approval_parking_capacity_exhausted",
            )
        entry["lifecycle_state"] = _PARKED
        entry["approval_park_count"] = int(entry["approval_park_count"]) + 1
        self._state["approval_park_count"] = (
            int(self._state["approval_park_count"]) + 1
        )
        return self._event(
            event_type="approval_wait_parked",
            outcome="parked",
            request_id=request_id,
            lifecycle_state=_PARKED,
        )

    def resume(self, request_id: str) -> AgenticToolApprovalParkingEvent:
        with self._lock:
            return self._resume(request_id)

    def _resume(self, request_id: str) -> AgenticToolApprovalParkingEvent:
        request_id, entry = self._active_entry(request_id, expected_state=_PARKED)
        available = self.config.total_executor_capacity - self._executor_leases_used()
        if available <= self.config.reserved_executor_capacity:
            return self._capacity_rejected(
                request_id=request_id,
                lifecycle_state=_PARKED,
                failure_reason="reserved_executor_capacity",
            )
        entry["lifecycle_state"] = _EXECUTING
        entry["executor_lease_acquisition_count"] = (
            int(entry["executor_lease_acquisition_count"]) + 1
        )
        self._state["executor_lease_acquisition_count"] = (
            int(self._state["executor_lease_acquisition_count"]) + 1
        )
        return self._event(
            event_type="approval_wait_resumed",
            outcome="resumed",
            request_id=request_id,
            lifecycle_state=_EXECUTING,
        )

    def release(
        self,
        request_id: str,
        *,
        reason: str,
    ) -> AgenticToolApprovalParkingEvent:
        with self._lock:
            return self._release(request_id, reason=reason)

    def _release(
        self,
        request_id: str,
        *,
        reason: str,
    ) -> AgenticToolApprovalParkingEvent:
        request_id = self._request_id(request_id)
        if reason not in _RELEASE_REASONS:
            raise AgenticToolApprovalParkingError(
                "Approval parking release reason is unsupported."
            )
        entry = self._entries().get(request_id)
        if entry is None:
            self._state["release_suppression_count"] = (
                int(self._state["release_suppression_count"]) + 1
            )
            return self._event(
                event_type="release_suppressed",
                outcome="unknown_request",
                request_id=request_id,
                lifecycle_state="not_started",
                release_reason=reason,
            )
        lifecycle_state = str(entry["lifecycle_state"])
        if lifecycle_state == _RELEASED:
            self._state["release_suppression_count"] = (
                int(self._state["release_suppression_count"]) + 1
            )
            return self._event(
                event_type="release_suppressed",
                outcome="already_released",
                request_id=request_id,
                lifecycle_state=_RELEASED,
                release_reason=str(entry["release_reason"]),
            )
        entry["lifecycle_state"] = _RELEASED
        entry["release_reason"] = reason
        self._state["released_request_count"] = (
            int(self._state["released_request_count"]) + 1
        )
        release_reason_counts = self._release_reason_counts()
        release_reason_counts[reason] = int(release_reason_counts[reason]) + 1
        event = self._event(
            event_type="turn_released",
            outcome="released",
            request_id=request_id,
            lifecycle_state=_RELEASED,
            release_reason=reason,
        )
        self._released_tombstone_order().append(request_id)
        self._prune_released_tombstones()
        return event

    def release_all_for_runtime_reload(
        self,
    ) -> tuple[AgenticToolApprovalParkingEvent, ...]:
        with self._lock:
            active_request_ids = sorted(
                request_id
                for request_id, entry in self._entries().items()
                if entry["lifecycle_state"] != _RELEASED
            )
            return tuple(
                self.release(request_id, reason="runtime_reload")
                for request_id in active_request_ids
            )

    def state_snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._state_snapshot()

    def _state_snapshot(self) -> dict[str, object]:
        entries = [
            {"request_id": request_id, **copy.deepcopy(entry)}
            for request_id, entry in sorted(self._entries().items())
        ]
        return {
            "schema_version": AGENTIC_TOOL_PARKING_STATE_SCHEMA_VERSION,
            "config_fingerprint": self._config_fingerprint(),
            "entries": entries,
            "released_tombstone_order": list(self._released_tombstone_order()),
            "release_reason_counts": dict(self._release_reason_counts()),
            **{
                field: int(self._state[field])
                for field in _STATE_COUNTER_FIELDS
            },
        }

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            return self._diagnostics()

    def _diagnostics(self) -> dict[str, object]:
        entries = self._entries()
        lifecycle_counts = Counter(
            str(entry["lifecycle_state"]) for entry in entries.values()
        )
        release_reason_counts = self._release_reason_counts()
        executor_leases_used = self._executor_leases_used()
        parking_permits_used = self._parking_permits_used()
        return {
            "schema_version": AGENTIC_TOOL_PARKING_DIAGNOSTIC_SCHEMA_VERSION,
            "total_executor_capacity": self.config.total_executor_capacity,
            "reserved_executor_capacity": self.config.reserved_executor_capacity,
            "executor_leases_used": executor_leases_used,
            "executor_capacity_available": (
                self.config.total_executor_capacity - executor_leases_used
            ),
            "executor_resume_capacity_available": max(
                self.config.total_executor_capacity
                - self.config.reserved_executor_capacity
                - executor_leases_used,
                0,
            ),
            "max_parked_approval_waits": self.config.max_parked_approval_waits,
            "parking_permits_used": parking_permits_used,
            "parking_permits_available": (
                self.config.max_parked_approval_waits - parking_permits_used
            ),
            "executing_request_count": lifecycle_counts[_EXECUTING],
            "parked_request_count": lifecycle_counts[_PARKED],
            "released_request_count": int(self._state["released_request_count"]),
            "max_released_tombstones": self.config.max_released_tombstones,
            "retained_released_tombstone_count": lifecycle_counts[_RELEASED],
            "executor_lease_acquisition_count": int(
                self._state["executor_lease_acquisition_count"]
            ),
            "approval_park_count": int(self._state["approval_park_count"]),
            "capacity_rejection_count": int(
                self._state["capacity_rejection_count"]
            ),
            "release_suppression_count": int(
                self._state["release_suppression_count"]
            ),
            "release_reason_counts": {
                reason: int(release_reason_counts[reason])
                for reason in sorted(_RELEASE_REASONS)
            },
        }

    def _restore_state(
        self, state: Mapping[str, object] | None
    ) -> dict[str, object]:
        if state is None:
            return {
                "entries": {},
                "released_tombstone_order": [],
                "release_reason_counts": {
                    reason: 0 for reason in sorted(_RELEASE_REASONS)
                },
                "capacity_rejection_count": 0,
                "release_suppression_count": 0,
                "event_sequence": 0,
                "released_request_count": 0,
                "executor_lease_acquisition_count": 0,
                "approval_park_count": 0,
            }
        expected_keys = {
            "schema_version",
            "config_fingerprint",
            "entries",
            "released_tombstone_order",
            "release_reason_counts",
            *_STATE_COUNTER_FIELDS,
        }
        if set(state) != expected_keys:
            raise AgenticToolApprovalParkingError(
                "Approval parking state fields do not match the v1 contract."
            )
        if state.get("schema_version") != AGENTIC_TOOL_PARKING_STATE_SCHEMA_VERSION:
            raise AgenticToolApprovalParkingError(
                "Unsupported approval parking state schema version."
            )
        if state.get("config_fingerprint") != self._config_fingerprint():
            raise AgenticToolApprovalParkingError(
                "Approval parking state does not match the configured capacity."
            )
        restored: dict[str, object] = {}
        for field in _STATE_COUNTER_FIELDS:
            value = state.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgenticToolApprovalParkingError(
                    f"Approval parking state {field} must be a non-negative integer."
                )
            restored[field] = value
        raw_entries = state.get("entries")
        if not isinstance(raw_entries, list):
            raise AgenticToolApprovalParkingError(
                "Approval parking state entries must be a list."
            )
        entries: dict[str, dict[str, object]] = {}
        for raw_entry in raw_entries:
            request_id, entry = self._restore_entry(raw_entry)
            if request_id in entries:
                raise AgenticToolApprovalParkingError(
                    "Approval parking state request ids must be unique."
                )
            entries[request_id] = entry
        restored["entries"] = entries
        raw_release_reason_counts = state.get("release_reason_counts")
        if (
            not isinstance(raw_release_reason_counts, dict)
            or set(raw_release_reason_counts) != _RELEASE_REASONS
        ):
            raise AgenticToolApprovalParkingError(
                "Approval parking release reason counts do not match the v1 contract."
            )
        release_reason_counts: dict[str, int] = {}
        for reason in sorted(_RELEASE_REASONS):
            release_reason_counts[reason] = self._non_negative_int(
                raw_release_reason_counts[reason], f"release_reason_counts.{reason}"
            )
        if sum(release_reason_counts.values()) != restored["released_request_count"]:
            raise AgenticToolApprovalParkingError(
                "Approval parking release reason counts must equal released requests."
            )
        restored["release_reason_counts"] = release_reason_counts

        raw_tombstone_order = state.get("released_tombstone_order")
        if not isinstance(raw_tombstone_order, list):
            raise AgenticToolApprovalParkingError(
                "Released approval tombstone order must be a list."
            )
        tombstone_order = [self._request_id(value) for value in raw_tombstone_order]
        if len(tombstone_order) != len(set(tombstone_order)):
            raise AgenticToolApprovalParkingError(
                "Released approval tombstone request ids must be unique."
            )
        released_entry_ids = {
            request_id
            for request_id, entry in entries.items()
            if entry["lifecycle_state"] == _RELEASED
        }
        if set(tombstone_order) != released_entry_ids:
            raise AgenticToolApprovalParkingError(
                "Released approval tombstone order must match retained entries."
            )
        if len(tombstone_order) > self.config.max_released_tombstones:
            raise AgenticToolApprovalParkingError(
                "Approval parking state exceeds released tombstone capacity."
            )
        if len(tombstone_order) > int(restored["released_request_count"]):
            raise AgenticToolApprovalParkingError(
                "Retained approval tombstones exceed released requests."
            )
        restored["released_tombstone_order"] = tombstone_order
        if self._executor_leases_used(entries) > self.config.total_executor_capacity:
            raise AgenticToolApprovalParkingError(
                "Approval parking state exceeds total executor capacity."
            )
        if self._parking_permits_used(entries) > self.config.max_parked_approval_waits:
            raise AgenticToolApprovalParkingError(
                "Approval parking state exceeds parking capacity."
            )
        if sum(
            int(entry["executor_lease_acquisition_count"])
            for entry in entries.values()
        ) > int(restored["executor_lease_acquisition_count"]):
            raise AgenticToolApprovalParkingError(
                "Approval parking entry acquisitions exceed the cumulative count."
            )
        if sum(int(entry["approval_park_count"]) for entry in entries.values()) > int(
            restored["approval_park_count"]
        ):
            raise AgenticToolApprovalParkingError(
                "Approval parking entry parks exceed the cumulative count."
            )
        return restored

    def _restore_entry(
        self, raw_entry: object
    ) -> tuple[str, dict[str, object]]:
        expected_keys = {
            "request_id",
            "lifecycle_state",
            "release_reason",
            "executor_lease_acquisition_count",
            "approval_park_count",
        }
        if not isinstance(raw_entry, dict) or set(raw_entry) != expected_keys:
            raise AgenticToolApprovalParkingError(
                "Approval parking ledger entry fields do not match the v1 contract."
            )
        request_id = self._request_id(raw_entry.get("request_id"))
        lifecycle_state = raw_entry.get("lifecycle_state")
        release_reason = raw_entry.get("release_reason")
        if lifecycle_state not in _LIFECYCLE_STATES:
            raise AgenticToolApprovalParkingError(
                "Approval parking lifecycle state is unsupported."
            )
        if not isinstance(release_reason, str):
            raise AgenticToolApprovalParkingError(
                "Approval parking release reason must be a string."
            )
        if lifecycle_state == _RELEASED and release_reason not in _RELEASE_REASONS:
            raise AgenticToolApprovalParkingError(
                "Released approval parking entries require a release reason."
            )
        if lifecycle_state != _RELEASED and release_reason:
            raise AgenticToolApprovalParkingError(
                "Active approval parking entries cannot have a release reason."
            )
        executor_acquisitions = self._positive_int(
            raw_entry.get("executor_lease_acquisition_count"),
            "executor_lease_acquisition_count",
        )
        approval_parks = self._non_negative_int(
            raw_entry.get("approval_park_count"), "approval_park_count"
        )
        if lifecycle_state == _PARKED and approval_parks < 1:
            raise AgenticToolApprovalParkingError(
                "Parked approval entries require parking evidence."
            )
        if approval_parks > executor_acquisitions:
            raise AgenticToolApprovalParkingError(
                "Approval park count cannot exceed executor acquisitions."
            )
        return request_id, {
            "lifecycle_state": lifecycle_state,
            "release_reason": release_reason,
            "executor_lease_acquisition_count": executor_acquisitions,
            "approval_park_count": approval_parks,
        }

    def _active_entry(
        self, request_id: object, *, expected_state: str
    ) -> tuple[str, dict[str, object]]:
        normalized_request_id = self._request_id(request_id)
        entry = self._entries().get(normalized_request_id)
        if entry is None:
            raise AgenticToolApprovalParkingError(
                "Approval parking request has not acquired an executor lease."
            )
        if entry["lifecycle_state"] != expected_state:
            raise AgenticToolApprovalParkingError(
                "Approval parking request is in an invalid lifecycle state."
            )
        return normalized_request_id, entry

    def _capacity_rejected(
        self,
        *,
        request_id: str,
        lifecycle_state: str,
        failure_reason: str,
    ) -> AgenticToolApprovalParkingEvent:
        self._state["capacity_rejection_count"] = (
            int(self._state["capacity_rejection_count"]) + 1
        )
        return self._event(
            event_type="capacity_rejected",
            outcome="rejected",
            request_id=request_id,
            lifecycle_state=lifecycle_state,
            failure_reason=failure_reason,
        )

    def _event(
        self,
        *,
        event_type: str,
        outcome: str,
        request_id: str,
        lifecycle_state: str,
        release_reason: str = "",
        failure_reason: str = "",
    ) -> AgenticToolApprovalParkingEvent:
        sequence = int(self._state["event_sequence"]) + 1
        self._state["event_sequence"] = sequence
        return AgenticToolApprovalParkingEvent(
            sequence=sequence,
            event_type=event_type,
            outcome=outcome,
            request_id=request_id,
            lifecycle_state=lifecycle_state,
            release_reason=release_reason,
            failure_reason=failure_reason,
        )

    def _entries(self) -> dict[str, dict[str, object]]:
        entries = self._state["entries"]
        if not isinstance(entries, dict):
            raise AgenticToolApprovalParkingError(
                "Approval parking state entries are invalid."
            )
        return entries

    def _released_tombstone_order(self) -> list[str]:
        order = self._state["released_tombstone_order"]
        if not isinstance(order, list):
            raise AgenticToolApprovalParkingError(
                "Released approval tombstone order is invalid."
            )
        return order

    def _release_reason_counts(self) -> dict[str, int]:
        counts = self._state["release_reason_counts"]
        if not isinstance(counts, dict):
            raise AgenticToolApprovalParkingError(
                "Approval parking release reason counts are invalid."
            )
        return counts

    def _prune_released_tombstones(self) -> None:
        order = self._released_tombstone_order()
        entries = self._entries()
        while len(order) > self.config.max_released_tombstones:
            request_id = order.pop(0)
            entry = entries.get(request_id)
            if entry is None or entry["lifecycle_state"] != _RELEASED:
                raise AgenticToolApprovalParkingError(
                    "Released approval tombstone ledger is inconsistent."
                )
            del entries[request_id]

    def _executor_leases_used(
        self, entries: Mapping[str, Mapping[str, object]] | None = None
    ) -> int:
        source = entries if entries is not None else self._entries()
        return sum(entry["lifecycle_state"] == _EXECUTING for entry in source.values())

    def _parking_permits_used(
        self, entries: Mapping[str, Mapping[str, object]] | None = None
    ) -> int:
        source = entries if entries is not None else self._entries()
        return sum(entry["lifecycle_state"] == _PARKED for entry in source.values())

    def _config_fingerprint(self) -> str:
        encoded = json.dumps(
            self.config.as_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _request_id(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AgenticToolApprovalParkingError(
                "Approval parking request id is required."
            )
        return value.strip()

    @staticmethod
    def _positive_int(value: object, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise AgenticToolApprovalParkingError(
                f"Approval parking entry {field} must be a positive integer."
            )
        return value

    @staticmethod
    def _non_negative_int(value: object, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AgenticToolApprovalParkingError(
                f"Approval parking entry {field} must be a non-negative integer."
            )
        return value
