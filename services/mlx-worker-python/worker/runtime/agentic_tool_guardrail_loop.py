from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from worker.runtime.agentic_tools import (
    AgenticToolExecutionResult,
    AgenticToolPrerequisite,
    DeterministicAgenticToolRuntime,
    admit_agentic_tool_calls,
    heal_agentic_tool_calls,
)
from worker.runtime.stream_assembler import AssemblyDelta
from worker.runtime.tool_registry import ToolRegistry, agentic_tool_catalog_registry

AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION = "melix.agentic_tool_guardrail_state.v1"
AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION = "melix.agentic_tool_guardrail_config.v1"
AGENTIC_TOOL_GUARDRAIL_EVENT_SCHEMA_VERSION = "melix.agentic_tool_guardrail_event.v1"
AGENTIC_TOOL_GUARDRAIL_DIAGNOSTIC_SCHEMA_VERSION = (
    "melix.agentic_tool_guardrail_diagnostic.v1"
)

_STATE_COUNTER_FIELDS = (
    "responses_seen",
    "healed_response_count",
    "admission_rejection_count",
    "malformed_response_count",
    "tool_execution_count",
    "tool_failure_count",
    "replay_suppression_count",
    "duplicate_execution_count",
    "retry_nudge_count",
    "terminal_failure_count",
    "consecutive_malformed_responses",
    "consecutive_tool_failures",
    "event_sequence",
)
_REQUIRED_TOOL_LIFECYCLE_STATES = frozenset(
    {"required", "authorized", "executing", "completed", "retired"}
)
_EXECUTION_LEDGER_LIFECYCLE_STATES = frozenset(
    {"authorized", "executing", "completed", "retired"}
)


class AgenticToolGuardrailLoopError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        event: AgenticToolGuardrailEvent | None = None,
    ) -> None:
        super().__init__(message)
        self.event = event


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailConfig:
    request_id: str
    required_tools: tuple[str, ...] = ()
    prerequisites: tuple[AgenticToolPrerequisite, ...] = ()
    max_consecutive_malformed_responses: int = 2
    max_consecutive_tool_failures: int = 2
    max_turns: int = 12

    def __post_init__(self) -> None:
        request_id = self.request_id.strip()
        required_tools = tuple(
            dict.fromkeys(name.strip() for name in self.required_tools if name.strip())
        )
        if not request_id:
            raise AgenticToolGuardrailLoopError("A guardrail loop request id is required.")
        if self.max_consecutive_malformed_responses < 0:
            raise AgenticToolGuardrailLoopError("Malformed-response budget cannot be negative.")
        if self.max_consecutive_tool_failures < 0:
            raise AgenticToolGuardrailLoopError("Tool-failure budget cannot be negative.")
        if self.max_turns < 1:
            raise AgenticToolGuardrailLoopError("Guardrail loop max turns must be positive.")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "required_tools", required_tools)
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION,
            "request_id": self.request_id,
            "required_tools": list(self.required_tools),
            "prerequisites": [
                {
                    "tool_name": item.tool_name,
                    "required_tool_name": item.required_tool_name,
                    "argument_match_keys": list(item.argument_match_keys),
                }
                for item in self.prerequisites
            ],
            "max_consecutive_malformed_responses": (
                self.max_consecutive_malformed_responses
            ),
            "max_consecutive_tool_failures": self.max_consecutive_tool_failures,
            "max_turns": self.max_turns,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgenticToolGuardrailConfig:
        if payload.get("schema_version") != AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION:
            raise AgenticToolGuardrailLoopError(
                "Unsupported guardrail config schema version."
            )
        required_tools = _string_tuple(payload.get("required_tools"), "required_tools")
        raw_prerequisites = payload.get("prerequisites")
        if not isinstance(raw_prerequisites, list):
            raise AgenticToolGuardrailLoopError("Guardrail prerequisites must be a list.")
        prerequisites: list[AgenticToolPrerequisite] = []
        for item in raw_prerequisites:
            if not isinstance(item, dict):
                raise AgenticToolGuardrailLoopError(
                    "Each guardrail prerequisite must be an object."
                )
            try:
                prerequisites.append(
                    AgenticToolPrerequisite(
                        tool_name=_required_string(item.get("tool_name"), "tool_name"),
                        required_tool_name=_required_string(
                            item.get("required_tool_name"),
                            "required_tool_name",
                        ),
                        argument_match_keys=_string_tuple(
                            item.get("argument_match_keys"),
                            "argument_match_keys",
                        ),
                    )
                )
            except ValueError as exc:
                raise AgenticToolGuardrailLoopError(str(exc)) from exc
        return cls(
            request_id=_required_string(payload.get("request_id"), "request_id"),
            required_tools=required_tools,
            prerequisites=tuple(prerequisites),
            max_consecutive_malformed_responses=_required_int(
                payload.get("max_consecutive_malformed_responses"),
                "max_consecutive_malformed_responses",
            ),
            max_consecutive_tool_failures=_required_int(
                payload.get("max_consecutive_tool_failures"),
                "max_consecutive_tool_failures",
            ),
            max_turns=_required_int(payload.get("max_turns"), "max_turns"),
        )


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailNudge:
    kind: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "message": self.message}


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailEvent:
    sequence: int
    event_type: str
    outcome: str
    nudge_type: str = ""
    failure_reason: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    consecutive_malformed_responses: int = 0
    consecutive_tool_failures: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": AGENTIC_TOOL_GUARDRAIL_EVENT_SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "outcome": self.outcome,
            "nudge_type": self.nudge_type,
            "failure_reason": self.failure_reason,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "consecutive_malformed_responses": self.consecutive_malformed_responses,
            "consecutive_tool_failures": self.consecutive_tool_failures,
        }


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailTurn:
    action: str
    nudge: AgenticToolGuardrailNudge | None
    tool_results: tuple[AgenticToolExecutionResult, ...]
    events: tuple[AgenticToolGuardrailEvent, ...]
    final_text: str = ""
    failure_reason: str = ""


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailRun:
    outcome: str
    final_text: str
    turns: tuple[AgenticToolGuardrailTurn, ...]
    diagnostics: dict[str, object]
    state: dict[str, object]


@dataclass(frozen=True, slots=True)
class AgenticToolGuardrailModelDirective:
    tool_choice: str
    context_messages: tuple[dict[str, str], ...] = ()
    tool_observations: tuple[AgenticToolExecutionResult, ...] = ()
    nudge: AgenticToolGuardrailNudge | None = None


class AgenticToolGuardrailLoop:
    def __init__(
        self,
        *,
        config: AgenticToolGuardrailConfig,
        registry: ToolRegistry | None = None,
        runtime: DeterministicAgenticToolRuntime | None = None,
        state: dict[str, object] | None = None,
    ) -> None:
        self.config = config
        self._registry = registry or agentic_tool_catalog_registry()
        self._runtime = runtime or DeterministicAgenticToolRuntime(registry=self._registry)
        self._state = self._restore_state(state)
        configured_tools = set(config.required_tools)
        for prerequisite in config.prerequisites:
            configured_tools.add(prerequisite.tool_name)
            configured_tools.add(prerequisite.required_tool_name)
        unknown_configured_tools = configured_tools.difference(self._registry.names())
        if unknown_configured_tools:
            unknown_tool = sorted(unknown_configured_tools)[0]
            raise AgenticToolGuardrailLoopError(
                "Guardrail required and prerequisite tools must exist in the selected "
                "registry: "
                + ", ".join(sorted(unknown_configured_tools)),
                event=AgenticToolGuardrailEvent(
                    sequence=0,
                    event_type="guardrail_preflight",
                    outcome="rejected",
                    failure_reason="configured_tool_unavailable",
                    tool_name=unknown_tool,
                ),
            )

    def handle_response(self, response: object) -> AgenticToolGuardrailTurn:
        events = self._preflight_events()
        results: list[AgenticToolExecutionResult] = []
        if bool(self._state["terminal"]):
            outcome = str(self._state["final_outcome"])
            events.append(self._event("response_ignored", outcome))
            return AgenticToolGuardrailTurn(
                action="complete" if outcome == "completed" else "failed",
                nudge=None,
                tool_results=(),
                events=tuple(events),
                failure_reason=str(self._state["final_failure_reason"]),
            )
        if int(self._state["responses_seen"]) >= self.config.max_turns:
            return self.exhaust_turn_budget(events=events)

        self._state["responses_seen"] = int(self._state["responses_seen"]) + 1
        events.append(self._event("response_received", "received"))
        if bool(self._state["awaiting_final_answer"]):
            return self._handle_final_response(response, events=events)

        decision = heal_agentic_tool_calls(
            response,
            registry=self._registry,
            attempt_index=int(self._state["consecutive_malformed_responses"]) + 1,
            max_retry_nudges=self.config.max_consecutive_malformed_responses,
        )
        healing_receipt = decision.receipts[0] if decision.receipts else {}
        accepts_direct_final = not decision.healed and self._accepts_direct_final_response(
            response,
            decision.receipts,
        )
        if decision.healed:
            healing_outcome = "healed"
        elif accepts_direct_final:
            healing_outcome = "not_applicable"
        else:
            healing_outcome = "rejected"
        events.append(
            self._event(
                "healing_decision",
                healing_outcome,
                failure_reason=(
                    ""
                    if accepts_direct_final
                    else str(healing_receipt.get("nudge_reason", ""))
                ),
            )
        )
        if not decision.healed:
            if accepts_direct_final:
                return self._complete_final_response(response, events=events)
            kind = self._healing_failure_kind(response, decision.receipts)
            return self._malformed_turn(kind, events=events, results=results)

        self._state["healed_response_count"] = int(self._state["healed_response_count"]) + 1
        completed_calls = self._completed_calls()
        ledger = self._execution_ledger()

        for call_index, call in enumerate(decision.normalized_calls):
            admission = admit_agentic_tool_calls(
                [call],
                registry=self._registry,
                prerequisites=self.config.prerequisites,
                completed_tool_calls=completed_calls,
                attempt_index=1,
                max_retry_nudges=0,
            )
            admission_receipt = admission.receipts[0] if admission.receipts else {}
            events.append(
                self._event(
                    "admission_decision",
                    "admitted" if admission.admitted else "rejected",
                    failure_reason=str(admission_receipt.get("failure_class", "")),
                    tool_call_id=str(call.get("id", "")),
                    tool_name=str(call.get("name", "")),
                )
            )
            if not admission.admitted:
                self._state["admission_rejection_count"] = (
                    int(self._state["admission_rejection_count"]) + 1
                )
                kind = str(admission_receipt.get("failure_class") or "tool_admission_rejected")
                return self._malformed_turn(kind, events=events, results=results)

            normalized_call = admission.normalized_calls[0]
            call_id = str(normalized_call["id"])
            tool_name = str(normalized_call["name"])
            arguments = dict(normalized_call["arguments"])
            try:
                fingerprint = _tool_call_fingerprint(tool_name=tool_name, arguments=arguments)
            except (TypeError, ValueError):
                return self._malformed_turn(
                    "invalid_arguments",
                    events=events,
                    results=results,
                )
            previous_entry = ledger.get(call_id)
            if previous_entry is not None:
                if previous_entry["fingerprint"] != fingerprint:
                    return self._terminal_turn(
                        "tool_call_identity_conflict",
                        events=events,
                        results=results,
                        tool_call_id=call_id,
                        tool_name=tool_name,
                    )
                self._state["replay_suppression_count"] = (
                    int(self._state["replay_suppression_count"]) + 1
                )
                self._state["consecutive_malformed_responses"] = 0
                events.append(
                    self._event(
                        "replay_suppressed",
                        "suppressed",
                        tool_call_id=call_id,
                        tool_name=tool_name,
                    )
                )
                continue

            ledger[call_id] = {
                "fingerprint": fingerprint,
                "tool_name": tool_name,
                "lifecycle_state": "authorized",
            }
            self._set_required_tool_lifecycle(tool_name, "authorized")
            events.append(
                self._event(
                    "tool_lifecycle",
                    "authorized",
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )
            )

            # Record executing before entering the adapter. A timeout or failure
            # may still have produced an external side effect and must not replay.
            ledger[call_id]["lifecycle_state"] = "executing"
            self._set_required_tool_lifecycle(tool_name, "executing")
            events.append(
                self._event(
                    "tool_lifecycle",
                    "executing",
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )
            )
            self._state["consecutive_malformed_responses"] = 0
            self._state["tool_execution_count"] = int(self._state["tool_execution_count"]) + 1
            try:
                result = self._runtime.execute(
                    tool_name=tool_name,
                    arguments=arguments,
                    tool_call_id=call_id,
                )
            except Exception:
                events.append(
                    self._event(
                        "tool_execution",
                        "adapter_error",
                        failure_reason="tool_adapter_error",
                        tool_call_id=call_id,
                        tool_name=tool_name,
                    )
                )
                return self._tool_failure_turn(
                    "tool_adapter_error",
                    events=events,
                    results=results,
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )
            results.append(result)
            events.append(
                self._event(
                    "tool_execution",
                    result.status,
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )
            )
            if result.status != "completed":
                return self._tool_failure_turn(
                    "tool_timeout" if result.status == "timeout" else "tool_execution_failed",
                    events=events,
                    results=results,
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )

            self._state["consecutive_tool_failures"] = 0
            completed_call = {
                "id": call_id,
                "name": tool_name,
                "arguments": arguments,
            }
            completed_calls.append(completed_call)
            self._state["completed_tool_calls"] = completed_calls
            ledger[call_id]["lifecycle_state"] = "completed"
            self._set_required_tool_lifecycle(tool_name, "completed")
            events.append(
                self._event(
                    "tool_lifecycle",
                    "completed",
                    tool_call_id=call_id,
                    tool_name=tool_name,
                )
            )
            if (
                self._required_steps_complete()
                and call_index + 1 < len(decision.normalized_calls)
            ):
                self._retire_required_tools(events)
                for retired_call in decision.normalized_calls[call_index + 1 :]:
                    events.append(
                        self._event(
                            "tool_call_retired",
                            "retired",
                            failure_reason="required_steps_completed",
                            tool_call_id=str(retired_call.get("id", "")),
                            tool_name=str(retired_call.get("name", "")),
                        )
                    )
                break

        if self._required_steps_complete():
            self._retire_required_tools(events)
            self._state["awaiting_final_answer"] = True
            return self._nudge_turn(
                action="finalize",
                kind="required_steps_completed",
                events=events,
                results=results,
                is_retry=False,
            )
        return self._nudge_turn(
            action="continue",
            kind=(
                "required_steps_remaining"
                if self.config.required_tools
                else "tool_observation_ready"
            ),
            events=events,
            results=results,
            is_retry=False,
        )

    def state_snapshot(self) -> dict[str, object]:
        return copy.deepcopy(self._state)

    def diagnostics(self) -> dict[str, object]:
        completed_names = {str(call.get("name", "")) for call in self._completed_calls()}
        return {
            "schema_version": AGENTIC_TOOL_GUARDRAIL_DIAGNOSTIC_SCHEMA_VERSION,
            "request_id": self.config.request_id,
            "responses_seen": int(self._state["responses_seen"]),
            "healed_response_count": int(self._state["healed_response_count"]),
            "admission_rejection_count": int(self._state["admission_rejection_count"]),
            "malformed_response_count": int(self._state["malformed_response_count"]),
            "tool_execution_count": int(self._state["tool_execution_count"]),
            "tool_failure_count": int(self._state["tool_failure_count"]),
            "replay_suppression_count": int(self._state["replay_suppression_count"]),
            "duplicate_execution_count": int(self._state["duplicate_execution_count"]),
            "retry_nudge_count": int(self._state["retry_nudge_count"]),
            "terminal_failure_count": int(self._state["terminal_failure_count"]),
            "consecutive_malformed_responses": int(
                self._state["consecutive_malformed_responses"]
            ),
            "consecutive_tool_failures": int(self._state["consecutive_tool_failures"]),
            "last_nudge_type": str(self._state["last_nudge_type"]),
            "final_outcome": str(self._state["final_outcome"]),
            "final_failure_reason": str(self._state["final_failure_reason"]),
            "completed_required_tools": [
                name for name in self.config.required_tools if name in completed_names
            ],
        }

    def next_model_directive(
        self,
        nudge: AgenticToolGuardrailNudge | None = None,
        *,
        tool_observations: tuple[AgenticToolExecutionResult, ...] = (),
    ) -> AgenticToolGuardrailModelDirective:
        if bool(self._state["terminal"]) or bool(self._state["awaiting_final_answer"]):
            tool_choice = "none"
        elif self._missing_required_tools():
            tool_choice = "required"
        else:
            tool_choice = "auto"
        messages = (
            ({"role": "system", "content": nudge.message},)
            if nudge is not None
            else ()
        )
        return AgenticToolGuardrailModelDirective(
            tool_choice=tool_choice,
            context_messages=messages,
            tool_observations=tool_observations,
            nudge=nudge,
        )

    def exhaust_turn_budget(
        self,
        *,
        events: list[AgenticToolGuardrailEvent] | None = None,
    ) -> AgenticToolGuardrailTurn:
        budget_events = list(events) if events is not None else self._preflight_events()
        budget_events.append(self._event("turn_budget", "exhausted"))
        return self._terminal_turn(
            "turn_budget_exhausted",
            events=budget_events,
            results=[],
        )

    def _handle_final_response(
        self,
        response: object,
        *,
        events: list[AgenticToolGuardrailEvent],
    ) -> AgenticToolGuardrailTurn:
        decision = heal_agentic_tool_calls(
            response,
            registry=self._registry,
            attempt_index=int(self._state["consecutive_malformed_responses"]) + 1,
            max_retry_nudges=self.config.max_consecutive_malformed_responses,
        )
        if not isinstance(response, str):
            return self._malformed_turn("tools_retired", events=events, results=[])
        final_text = response.strip()
        if not final_text:
            return self._malformed_turn("final_response_required", events=events, results=[])
        if decision.healed or not self._is_plain_final_response(response, decision.receipts):
            return self._malformed_turn("tools_retired", events=events, results=[])
        return self._complete_final_response(final_text, events=events)

    def _complete_final_response(
        self,
        response: str,
        *,
        events: list[AgenticToolGuardrailEvent],
    ) -> AgenticToolGuardrailTurn:
        final_text = response.strip()
        self._state["terminal"] = True
        self._state["final_outcome"] = "completed"
        self._state["final_failure_reason"] = ""
        self._state["awaiting_final_answer"] = False
        self._state["consecutive_malformed_responses"] = 0
        events.append(self._event("loop_completed", "completed"))
        return AgenticToolGuardrailTurn(
            action="complete",
            nudge=None,
            tool_results=(),
            events=tuple(events),
            final_text=final_text,
        )

    def _accepts_direct_final_response(
        self,
        response: object,
        receipts: tuple[dict[str, Any], ...],
    ) -> bool:
        if self.config.required_tools:
            return False
        return self._is_plain_final_response(response, receipts)

    def _is_plain_final_response(
        self,
        response: object,
        receipts: tuple[dict[str, Any], ...],
    ) -> bool:
        if not isinstance(response, str) or not response.strip():
            return False
        if any(
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(tool_name)}\s*\(", response)
            for tool_name in self._registry.names()
        ):
            return False
        healing_receipt = receipts[0] if receipts else {}
        if healing_receipt.get("source_format") == "pseudo_tool_text_blob":
            return False
        return not any(
            receipt.get("schema_version") == "melix.agentic_tool_guardrail.v1"
            for receipt in receipts
        )

    def _malformed_turn(
        self,
        kind: str,
        *,
        events: list[AgenticToolGuardrailEvent],
        results: list[AgenticToolExecutionResult],
    ) -> AgenticToolGuardrailTurn:
        self._state["malformed_response_count"] = int(self._state["malformed_response_count"]) + 1
        self._state["consecutive_malformed_responses"] = (
            int(self._state["consecutive_malformed_responses"]) + 1
        )
        if (
            int(self._state["consecutive_malformed_responses"])
            > self.config.max_consecutive_malformed_responses
        ):
            return self._terminal_turn(
                "malformed_response_budget_exhausted",
                events=events,
                results=results,
            )
        return self._nudge_turn(
            action="retry",
            kind=kind,
            events=events,
            results=results,
        )

    def _tool_failure_turn(
        self,
        kind: str,
        *,
        events: list[AgenticToolGuardrailEvent],
        results: list[AgenticToolExecutionResult],
        tool_call_id: str,
        tool_name: str,
    ) -> AgenticToolGuardrailTurn:
        self._state["tool_failure_count"] = int(self._state["tool_failure_count"]) + 1
        self._state["consecutive_tool_failures"] = (
            int(self._state["consecutive_tool_failures"]) + 1
        )
        if (
            int(self._state["consecutive_tool_failures"])
            > self.config.max_consecutive_tool_failures
        ):
            return self._terminal_turn(
                "tool_failure_budget_exhausted",
                events=events,
                results=results,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )
        return self._nudge_turn(
            action="retry",
            kind=kind,
            events=events,
            results=results,
        )

    def _nudge_turn(
        self,
        *,
        action: str,
        kind: str,
        events: list[AgenticToolGuardrailEvent],
        results: list[AgenticToolExecutionResult],
        is_retry: bool = True,
    ) -> AgenticToolGuardrailTurn:
        nudge = AgenticToolGuardrailNudge(kind=kind, message=_nudge_message(kind))
        if is_retry:
            self._state["retry_nudge_count"] = int(self._state["retry_nudge_count"]) + 1
        self._state["last_nudge_type"] = kind
        events.append(
            self._event(
                "retry_nudge" if is_retry else "model_directive",
                action,
                nudge_type=kind,
            )
        )
        return AgenticToolGuardrailTurn(
            action=action,
            nudge=nudge,
            tool_results=tuple(results),
            events=tuple(events),
        )

    def _terminal_turn(
        self,
        failure_reason: str,
        *,
        events: list[AgenticToolGuardrailEvent],
        results: list[AgenticToolExecutionResult],
        tool_call_id: str = "",
        tool_name: str = "",
    ) -> AgenticToolGuardrailTurn:
        self._state["terminal"] = True
        self._state["final_outcome"] = "failed"
        self._state["final_failure_reason"] = failure_reason
        self._state["awaiting_final_answer"] = False
        self._state["terminal_failure_count"] = int(self._state["terminal_failure_count"]) + 1
        events.append(
            self._event(
                "terminal_failure",
                "failed",
                failure_reason=failure_reason,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )
        )
        return AgenticToolGuardrailTurn(
            action="failed",
            nudge=None,
            tool_results=tuple(results),
            events=tuple(events),
            failure_reason=failure_reason,
        )

    def _event(
        self,
        event_type: str,
        outcome: str,
        *,
        nudge_type: str = "",
        failure_reason: str = "",
        tool_call_id: str = "",
        tool_name: str = "",
    ) -> AgenticToolGuardrailEvent:
        sequence = int(self._state["event_sequence"]) + 1
        self._state["event_sequence"] = sequence
        return AgenticToolGuardrailEvent(
            sequence=sequence,
            event_type=event_type,
            outcome=outcome,
            nudge_type=nudge_type,
            failure_reason=failure_reason,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            consecutive_malformed_responses=int(
                self._state["consecutive_malformed_responses"]
            ),
            consecutive_tool_failures=int(self._state["consecutive_tool_failures"]),
        )

    def _preflight_events(self) -> list[AgenticToolGuardrailEvent]:
        if bool(self._state["preflight_event_emitted"]):
            return []
        self._state["preflight_event_emitted"] = True
        return [self._event("guardrail_preflight", "passed")]

    def _healing_failure_kind(
        self,
        response: object,
        receipts: tuple[dict[str, Any], ...],
    ) -> str:
        admission_receipt = next(
            (
                receipt
                for receipt in receipts
                if receipt.get("schema_version") == "melix.agentic_tool_guardrail.v1"
            ),
            {},
        )
        failure_class = str(admission_receipt.get("failure_class", ""))
        if failure_class:
            return failure_class
        healing_receipt = receipts[0] if receipts else {}
        source_format = str(healing_receipt.get("source_format", ""))
        if source_format == "pseudo_tool_text_blob":
            return "pseudo_tool_text_blob"
        if (
            source_format == "unparseable_tool_response"
            and isinstance(response, str)
            and response.strip()
            and self._missing_required_tools()
        ):
            return "premature_terminal"
        nudge_reason = str(healing_receipt.get("nudge_reason", ""))
        if nudge_reason == "tool_call_wire_shape_required":
            return "malformed_tool_call"
        return nudge_reason or "malformed_tool_call"

    def _completed_calls(self) -> list[dict[str, Any]]:
        value = self._state["completed_tool_calls"]
        if not isinstance(value, list):
            raise AgenticToolGuardrailLoopError("Guardrail state completed calls must be a list.")
        return value

    def _execution_ledger(self) -> dict[str, dict[str, str]]:
        value = self._state["execution_ledger"]
        if not isinstance(value, dict):
            raise AgenticToolGuardrailLoopError("Guardrail execution ledger must be an object.")
        return value  # type: ignore[return-value]

    def _required_tool_lifecycle(self) -> dict[str, str]:
        value = self._state["required_tool_lifecycle"]
        if not isinstance(value, dict):
            raise AgenticToolGuardrailLoopError(
                "Guardrail required tool lifecycle must be an object."
            )
        return value  # type: ignore[return-value]

    def _set_required_tool_lifecycle(self, tool_name: str, state: str) -> None:
        lifecycle = self._required_tool_lifecycle()
        if tool_name in lifecycle:
            lifecycle[tool_name] = state

    def _retire_required_tools(
        self, events: list[AgenticToolGuardrailEvent]
    ) -> None:
        lifecycle = self._required_tool_lifecycle()
        ledger = self._execution_ledger()
        required_tools = set(self.config.required_tools)
        for tool_name in required_tools:
            lifecycle[tool_name] = "retired"
        for call_id, entry in ledger.items():
            if (
                entry["tool_name"] in required_tools
                and entry["lifecycle_state"] == "completed"
            ):
                entry["lifecycle_state"] = "retired"
                events.append(
                    self._event(
                        "tool_lifecycle",
                        "retired",
                        tool_call_id=call_id,
                        tool_name=entry["tool_name"],
                    )
                )

    def _missing_required_tools(self) -> tuple[str, ...]:
        completed = {str(call.get("name", "")) for call in self._completed_calls()}
        return tuple(name for name in self.config.required_tools if name not in completed)

    def _required_steps_complete(self) -> bool:
        return bool(self.config.required_tools) and not self._missing_required_tools()

    def _restore_state(self, state: dict[str, object] | None) -> dict[str, object]:
        if state is None:
            return _new_guardrail_state(
                self.config.request_id, self.config.required_tools
            )
        if not isinstance(state, dict):
            raise AgenticToolGuardrailLoopError("Guardrail state must be an object.")
        restored = copy.deepcopy(state)
        if restored.get("schema_version") != AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION:
            raise AgenticToolGuardrailLoopError("Unsupported guardrail state schema version.")
        if restored.get("request_id") != self.config.request_id:
            raise AgenticToolGuardrailLoopError("Guardrail state request id does not match config.")
        expected_keys = set(
            _new_guardrail_state(self.config.request_id, self.config.required_tools)
        )
        if set(restored) != expected_keys:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state fields do not match the v1 schema."
            )
        for field in _STATE_COUNTER_FIELDS:
            value = restored[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgenticToolGuardrailLoopError(
                    f"Guardrail state {field} must be a nonnegative integer."
                )
        for field in ("terminal", "awaiting_final_answer", "preflight_event_emitted"):
            if not isinstance(restored[field], bool):
                raise AgenticToolGuardrailLoopError(
                    f"Guardrail state {field} must be a boolean."
                )
        for field in ("last_nudge_type", "final_outcome", "final_failure_reason"):
            if not isinstance(restored[field], str):
                raise AgenticToolGuardrailLoopError(
                    f"Guardrail state {field} must be a string."
                )

        completed_calls = restored["completed_tool_calls"]
        if not isinstance(completed_calls, list):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state completed_tool_calls must be a list."
            )
        execution_ledger = restored["execution_ledger"]
        if not isinstance(execution_ledger, dict):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state execution_ledger must be an object."
            )
        required_tool_lifecycle = restored["required_tool_lifecycle"]
        if (
            not isinstance(required_tool_lifecycle, dict)
            or set(required_tool_lifecycle) != set(self.config.required_tools)
            or any(
                not isinstance(state, str)
                or state not in _REQUIRED_TOOL_LIFECYCLE_STATES
                for state in required_tool_lifecycle.values()
            )
        ):
            raise AgenticToolGuardrailLoopError(
                "Guardrail required tool lifecycle does not match config."
            )

        registry_names = set(self._registry.names())
        for call_id, entry in execution_ledger.items():
            if not isinstance(call_id, str) or not call_id.strip():
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state execution-ledger ids must be nonempty strings."
                )
            if not isinstance(entry, dict) or set(entry) != {
                "fingerprint",
                "tool_name",
                "lifecycle_state",
            }:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail execution-ledger entries must match the v1 shape."
                )
            fingerprint = entry["fingerprint"]
            tool_name = entry["tool_name"]
            lifecycle_state = entry["lifecycle_state"]
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
            ):
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state execution-ledger fingerprints must be lowercase SHA-256."
                )
            if not isinstance(tool_name, str) or tool_name not in registry_names:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail execution-ledger tools must exist in the selected registry."
                )
            if lifecycle_state not in _EXECUTION_LEDGER_LIFECYCLE_STATES:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail execution-ledger lifecycle state is unsupported."
                )

        completed_ids: set[str] = set()
        completed_names: set[str] = set()
        for completed_call in completed_calls:
            if not isinstance(completed_call, dict) or set(completed_call) != {
                "id",
                "name",
                "arguments",
            }:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state completed calls must match the v1 call shape."
                )
            call_id = completed_call["id"]
            tool_name = completed_call["name"]
            arguments = completed_call["arguments"]
            if not isinstance(call_id, str) or not call_id.strip() or call_id in completed_ids:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state completed-call ids must be unique nonempty strings."
                )
            if not isinstance(tool_name, str) or tool_name not in registry_names:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state completed-call tools must exist in the selected registry."
                )
            if not isinstance(arguments, dict) or not _is_json_value(arguments):
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state completed-call arguments must be a JSON object."
                )
            fingerprint = _tool_call_fingerprint(
                tool_name=tool_name,
                arguments=arguments,
            )
            ledger_entry = execution_ledger.get(call_id)
            if (
                not isinstance(ledger_entry, dict)
                or ledger_entry.get("fingerprint") != fingerprint
                or ledger_entry.get("tool_name") != tool_name
                or ledger_entry.get("lifecycle_state") not in {"completed", "retired"}
            ):
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state completed calls must match the execution ledger."
                )
            completed_ids.add(call_id)
            completed_names.add(tool_name)

        responses_seen = restored["responses_seen"]
        malformed_count = restored["malformed_response_count"]
        tool_execution_count = restored["tool_execution_count"]
        tool_failure_count = restored["tool_failure_count"]
        if responses_seen > self.config.max_turns:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state responses_seen exceeds the configured turn budget."
            )
        if restored["healed_response_count"] > responses_seen:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state healed responses cannot exceed responses_seen."
            )
        if malformed_count > responses_seen:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state malformed responses cannot exceed responses_seen."
            )
        if restored["admission_rejection_count"] > malformed_count:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state admission rejections cannot exceed malformed responses."
            )
        executing_entries = sum(
            entry["lifecycle_state"] == "executing"
            for entry in execution_ledger.values()
        )
        dispatched_entries = sum(
            entry["lifecycle_state"] != "authorized"
            for entry in execution_ledger.values()
        )
        if tool_execution_count != dispatched_entries:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state tool execution count must match the execution ledger."
            )
        if tool_failure_count != executing_entries:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state tool failures must match uncertain executions."
            )
        if restored["duplicate_execution_count"] != 0:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state cannot contain duplicate executions."
            )
        if restored["consecutive_malformed_responses"] > malformed_count:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state consecutive malformed responses exceed the total."
            )
        if restored["consecutive_tool_failures"] > tool_failure_count:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state consecutive tool failures exceed the total."
            )
        if restored["consecutive_malformed_responses"] > (
            self.config.max_consecutive_malformed_responses + 1
        ) or restored["consecutive_tool_failures"] > (
            self.config.max_consecutive_tool_failures + 1
        ):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state consecutive counters exceed the configured budgets."
            )
        if restored["terminal_failure_count"] not in (0, 1):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state terminal failure count must be zero or one."
            )

        for tool_name, lifecycle_state in required_tool_lifecycle.items():
            matching_ledger_states = {
                entry["lifecycle_state"]
                for entry in execution_ledger.values()
                if entry["tool_name"] == tool_name
            }
            if lifecycle_state == "required" and tool_name in completed_names:
                raise AgenticToolGuardrailLoopError(
                    "Required lifecycle cannot contain completed evidence."
                )
            if lifecycle_state in {"authorized", "executing", "completed", "retired"}:
                if lifecycle_state not in matching_ledger_states:
                    raise AgenticToolGuardrailLoopError(
                        "Required lifecycle must match execution-ledger evidence."
                    )
            if lifecycle_state in {"completed", "retired"} and tool_name not in completed_names:
                raise AgenticToolGuardrailLoopError(
                    "Completed required lifecycle needs a completed call."
                )

        preflight_emitted = restored["preflight_event_emitted"]
        event_sequence = restored["event_sequence"]
        if preflight_emitted != (event_sequence > 0):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state preflight evidence is inconsistent with event sequence."
            )
        if event_sequence < responses_seen:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state event sequence cannot trail responses_seen."
            )

        final_outcome = restored["final_outcome"]
        final_failure_reason = restored["final_failure_reason"]
        terminal = restored["terminal"]
        awaiting_final_answer = restored["awaiting_final_answer"]
        if final_outcome not in ("running", "completed", "failed"):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state final_outcome is not supported."
            )
        if final_outcome == "running":
            if terminal or final_failure_reason or restored["terminal_failure_count"] != 0:
                raise AgenticToolGuardrailLoopError(
                    "Running guardrail state cannot contain terminal outcome evidence."
                )
        elif not terminal or awaiting_final_answer:
            raise AgenticToolGuardrailLoopError(
                "Terminal guardrail state must be terminal and cannot await a final answer."
            )
        elif final_outcome == "completed":
            if final_failure_reason or restored["terminal_failure_count"] != 0:
                raise AgenticToolGuardrailLoopError(
                    "Completed guardrail state cannot contain failure evidence."
                )
        elif not final_failure_reason or restored["terminal_failure_count"] != 1:
            raise AgenticToolGuardrailLoopError(
                "Failed guardrail state requires one terminal failure and a reason."
            )

        all_required_retired = all(
            state == "retired" for state in required_tool_lifecycle.values()
        )
        if (awaiting_final_answer or final_outcome == "completed") and (
            self.config.required_tools and not all_required_retired
        ):
            raise AgenticToolGuardrailLoopError(
                "Final-answer state requires retired required steps."
            )

        budget_counters = (
            (
                "consecutive_malformed_responses",
                self.config.max_consecutive_malformed_responses,
                "malformed_response_budget_exhausted",
            ),
            (
                "consecutive_tool_failures",
                self.config.max_consecutive_tool_failures,
                "tool_failure_budget_exhausted",
            ),
        )
        for field, budget, exhausted_reason in budget_counters:
            counter = restored[field]
            exhaustion_failure = (
                final_outcome == "failed" and final_failure_reason == exhausted_reason
            )
            if counter > budget and not exhaustion_failure:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state over-budget consecutive counters require the "
                    "matching exhausted terminal failure."
                )
            if exhaustion_failure and counter != budget + 1:
                raise AgenticToolGuardrailLoopError(
                    "Guardrail state exhausted terminal failures require the exact "
                    "over-budget consecutive counter."
                )

        required_tools = set(self.config.required_tools)
        required_steps_complete = bool(required_tools) and required_tools.issubset(
            completed_names
        )
        if final_outcome == "completed" and responses_seen == 0:
            raise AgenticToolGuardrailLoopError(
                "Completed guardrail state requires at least one model response."
            )
        if final_outcome == "completed" and required_tools and not required_steps_complete:
            raise AgenticToolGuardrailLoopError(
                "Completed guardrail state requires all configured required steps."
            )
        if terminal and not preflight_emitted:
            raise AgenticToolGuardrailLoopError(
                "Terminal guardrail state requires guardrail preflight evidence."
            )
        if awaiting_final_answer and (
            terminal or final_outcome != "running" or not required_steps_complete
        ):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state can await a final answer only after required steps complete."
            )
        if (
            final_outcome == "running"
            and required_steps_complete
            and not awaiting_final_answer
        ):
            raise AgenticToolGuardrailLoopError(
                "Guardrail state must await a final answer after required steps complete."
            )
        return restored


def agentic_tool_calls_from_stream_deltas(
    deltas: Iterable[AssemblyDelta],
) -> tuple[dict[str, object], ...]:
    calls: list[dict[str, object]] = []
    for delta in deltas:
        tool_call = delta.tool_call
        if tool_call is None:
            continue
        try:
            arguments: object = json.loads(tool_call.arguments_json_fragment)
        except json.JSONDecodeError:
            arguments = tool_call.arguments_json_fragment
        calls.append(
            {
                "id": tool_call.call_id,
                "name": tool_call.tool_name,
                "arguments": arguments,
            }
        )
    return tuple(calls)


def agentic_tool_guardrail_inputs_from_execution_ext(
    ext: Mapping[str, str],
    *,
    registry: ToolRegistry | None = None,
) -> tuple[AgenticToolGuardrailConfig, dict[str, object] | None]:
    config_schema = ext.get("melix.agentic_guardrail.config_schema")
    if config_schema != AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION:
        raise AgenticToolGuardrailLoopError(
            "Worker execution metadata is missing a supported guardrail config schema."
        )
    config_payload = _json_object(
        ext.get("melix.agentic_guardrail.config_json"),
        "guardrail config",
    )
    config = AgenticToolGuardrailConfig.from_dict(config_payload)
    raw_state = ext.get("melix.agentic_guardrail.state_json")
    if raw_state is None:
        if "melix.agentic_guardrail.state_schema" in ext:
            raise AgenticToolGuardrailLoopError(
                "Guardrail state schema requires guardrail state JSON."
            )
        return config, None
    if (
        ext.get("melix.agentic_guardrail.state_schema")
        != AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION
    ):
        raise AgenticToolGuardrailLoopError(
            "Worker execution metadata has an unsupported guardrail state schema."
        )
    state = _json_object(raw_state, "guardrail state")
    if state.get("schema_version") != AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION:
        raise AgenticToolGuardrailLoopError(
            "Guardrail state JSON has an unsupported schema version."
        )
    if state.get("request_id") != config.request_id:
        raise AgenticToolGuardrailLoopError(
            "Guardrail state JSON request id does not match config."
        )
    validated_state = AgenticToolGuardrailLoop(
        config=config,
        registry=registry,
        state=state,
    ).state_snapshot()
    return config, validated_state


def run_guarded_agentic_tool_loop(
    responder: Callable[[AgenticToolGuardrailModelDirective], object],
    *,
    config: AgenticToolGuardrailConfig,
    registry: ToolRegistry | None = None,
    runtime: DeterministicAgenticToolRuntime | None = None,
    state: dict[str, object] | None = None,
) -> AgenticToolGuardrailRun:
    loop = AgenticToolGuardrailLoop(
        config=config,
        registry=registry,
        runtime=runtime,
        state=state,
    )
    turns: list[AgenticToolGuardrailTurn] = []
    nudge: AgenticToolGuardrailNudge | None = None
    tool_observations: tuple[AgenticToolExecutionResult, ...] = ()
    final_text = ""
    initial_diagnostics = loop.diagnostics()
    if initial_diagnostics["final_outcome"] != "running":
        return AgenticToolGuardrailRun(
            outcome=str(initial_diagnostics["final_outcome"]),
            final_text="",
            turns=(),
            diagnostics=initial_diagnostics,
            state=loop.state_snapshot(),
        )
    remaining_turns = max(
        0,
        config.max_turns - int(loop.state_snapshot()["responses_seen"]),
    )
    for _ in range(remaining_turns):
        response = responder(
            loop.next_model_directive(nudge, tool_observations=tool_observations)
        )
        turn = loop.handle_response(response)
        turns.append(turn)
        nudge = turn.nudge
        tool_observations = turn.tool_results
        if turn.action == "complete":
            final_text = turn.final_text
            break
        if turn.action == "failed":
            break
    else:
        turns.append(loop.exhaust_turn_budget())
    diagnostics = loop.diagnostics()
    return AgenticToolGuardrailRun(
        outcome=str(diagnostics["final_outcome"]),
        final_text=final_text,
        turns=tuple(turns),
        diagnostics=diagnostics,
        state=loop.state_snapshot(),
    )


def _new_guardrail_state(
    request_id: str, required_tools: Iterable[str]
) -> dict[str, object]:
    return {
        "schema_version": AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION,
        "request_id": request_id,
        "completed_tool_calls": [],
        "execution_ledger": {},
        "required_tool_lifecycle": {
            tool_name: "required" for tool_name in required_tools
        },
        "responses_seen": 0,
        "healed_response_count": 0,
        "admission_rejection_count": 0,
        "malformed_response_count": 0,
        "tool_execution_count": 0,
        "tool_failure_count": 0,
        "replay_suppression_count": 0,
        "duplicate_execution_count": 0,
        "retry_nudge_count": 0,
        "terminal_failure_count": 0,
        "consecutive_malformed_responses": 0,
        "consecutive_tool_failures": 0,
        "last_nudge_type": "",
        "final_outcome": "running",
        "final_failure_reason": "",
        "terminal": False,
        "awaiting_final_answer": False,
        "event_sequence": 0,
        "preflight_event_emitted": False,
    }


def _tool_call_fingerprint(*, tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"name": tool_name, "arguments": arguments},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_json_value(value: object) -> bool:
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgenticToolGuardrailLoopError(f"Guardrail {field} must be a string.")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AgenticToolGuardrailLoopError(f"Guardrail {field} must be a string list.")
    return tuple(value)


def _required_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgenticToolGuardrailLoopError(f"Guardrail {field} must be an integer.")
    return value


def _json_object(value: str | None, label: str) -> dict[str, object]:
    if value is None:
        raise AgenticToolGuardrailLoopError(f"Worker execution metadata is missing {label} JSON.")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AgenticToolGuardrailLoopError(
            f"Worker execution metadata contains invalid {label} JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise AgenticToolGuardrailLoopError(
            f"Worker execution metadata {label} JSON must be an object."
        )
    return payload


def _nudge_message(kind: str) -> str:
    messages = {
        "premature_terminal": "Required tool steps remain. Emit the next declared tool call.",
        "unknown_tool": "Use a tool name from the declared registry.",
        "invalid_arguments": "Emit a JSON object containing valid tool arguments.",
        "missing_required_arguments": "Emit every required argument for the selected tool.",
        "tool_prerequisite_violation": "Complete the matching prerequisite tool step first.",
        "pseudo_tool_text_blob": (
            "Emit a declared tool-call wire shape, not tool-like prose or content JSON."
        ),
        "tool_execution_failed": (
            "The tool failed. Retry with a new call id or choose another step."
        ),
        "tool_timeout": "The tool timed out. Retry with a new call id or choose another step.",
        "tool_adapter_error": "The tool adapter failed. Retry with a new call id.",
        "tools_retired": "Tool execution is complete. Return only the final answer.",
        "final_response_required": "Return a non-empty final answer without tool calls.",
        "required_steps_completed": (
            "All required tool steps are complete. Return the final answer."
        ),
        "required_steps_remaining": "Continue with the next required tool step.",
        "tool_observation_ready": (
            "Use the tool observation, then continue with a tool or return the final answer."
        ),
        "malformed_tool_call": "Emit one valid declared tool call.",
    }
    return messages.get(kind, "Correct the response and retry with a declared tool call.")


__all__ = [
    "AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION",
    "AGENTIC_TOOL_GUARDRAIL_DIAGNOSTIC_SCHEMA_VERSION",
    "AGENTIC_TOOL_GUARDRAIL_EVENT_SCHEMA_VERSION",
    "AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION",
    "AgenticToolGuardrailConfig",
    "AgenticToolGuardrailEvent",
    "AgenticToolGuardrailLoop",
    "AgenticToolGuardrailLoopError",
    "AgenticToolGuardrailModelDirective",
    "AgenticToolGuardrailNudge",
    "AgenticToolGuardrailRun",
    "AgenticToolGuardrailTurn",
    "agentic_tool_guardrail_inputs_from_execution_ext",
    "agentic_tool_calls_from_stream_deltas",
    "run_guarded_agentic_tool_loop",
]
