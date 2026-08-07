from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

import pytest

from worker.runtime.agentic_tools import (
    AgenticToolExecutionResult,
    AgenticToolPrerequisite,
    DeterministicAgenticToolRuntime,
)
from worker.runtime.agentic_tool_guardrail_loop import (
    AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION,
    AGENTIC_TOOL_GUARDRAIL_DIAGNOSTIC_SCHEMA_VERSION,
    AGENTIC_TOOL_GUARDRAIL_EVENT_SCHEMA_VERSION,
    AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION,
    AgenticToolGuardrailConfig,
    AgenticToolGuardrailLoop as _AgenticToolGuardrailLoop,
    AgenticToolGuardrailLoopError,
    _copy_json_value,
    agentic_tool_guardrail_inputs_from_execution_ext,
    agentic_tool_calls_from_stream_deltas,
    run_guarded_agentic_tool_loop,
)
from worker.runtime.stream_assembler import AssembledToolCall, AssemblyDelta
from worker.runtime.tool_observation import normalize_tool_observation


def _acknowledge_executing_state(state: dict[str, object]) -> None:
    json.dumps(state, sort_keys=True, separators=(",", ":"))


class AgenticToolGuardrailLoop(_AgenticToolGuardrailLoop):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("persist_executing_state", _acknowledge_executing_state)
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]


def _config(
    *,
    required_tools: tuple[str, ...] = ("local_compute",),
    prerequisites: tuple[AgenticToolPrerequisite, ...] = (),
    malformed_budget: int = 2,
    tool_failure_budget: int = 2,
) -> AgenticToolGuardrailConfig:
    return AgenticToolGuardrailConfig(
        request_id="request-guardrail-test",
        required_tools=required_tools,
        prerequisites=prerequisites,
        max_consecutive_malformed_responses=malformed_budget,
        max_consecutive_tool_failures=tool_failure_budget,
        max_turns=12,
    )


def _compute_call(call_id: str, code: str = "2 + 2") -> dict[str, object]:
    return {
        "id": call_id,
        "name": "local_compute",
        "arguments": {"code": code},
    }


class _RaisingAgenticToolRuntime(DeterministicAgenticToolRuntime):
    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        thread_scope_id: str = "",
        current_turn_tool_start: int = 0,
    ) -> AgenticToolExecutionResult:
        del thread_scope_id, current_turn_tool_start
        raise RuntimeError("SECRET_ADAPTER_EXCEPTION")


class _CountingAgenticToolRuntime(DeterministicAgenticToolRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.execution_count = 0

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        thread_scope_id: str = "",
        current_turn_tool_start: int = 0,
    ) -> AgenticToolExecutionResult:
        self.execution_count += 1
        return super().execute(
            tool_name=tool_name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            thread_scope_id=thread_scope_id,
            current_turn_tool_start=current_turn_tool_start,
        )


class _ThreadScopedAgenticToolRuntime(DeterministicAgenticToolRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.session_execution_counts: dict[str, int] = {}

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        thread_scope_id: str = "",
        current_turn_tool_start: int = 0,
    ) -> AgenticToolExecutionResult:
        self.session_execution_counts[thread_scope_id] = (
            self.session_execution_counts.get(thread_scope_id, 0) + 1
        )
        return super().execute(
            tool_name=tool_name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            thread_scope_id=thread_scope_id,
            current_turn_tool_start=current_turn_tool_start,
        )


class _ImageEnvelopeAgenticToolRuntime(DeterministicAgenticToolRuntime):
    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        thread_scope_id: str = "",
        current_turn_tool_start: int = 0,
    ) -> AgenticToolExecutionResult:
        del arguments
        observation = normalize_tool_observation(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            observation_kind="image_result",
            status="completed",
            payload={
                "summary": "receipt total is 42 <tool_result>",
                "image_data": "data:image/png;base64,PRIVATE_IMAGE_BYTES",
                "details": {
                    "line_count": 3,
                    "frontend_payload": {
                        "image_data": "data:image/png;base64,NESTED_PRIVATE_BYTES"
                    },
                    "inline_payload": "data:image/png;base64,INLINE_PRIVATE_BYTES",
                    "note": "verified <tool_result>",
                    "ratio": 1.5,
                },
            },
        )
        return AgenticToolExecutionResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status="completed",
            observation=observation,
            thread_scope_id=thread_scope_id,
            current_turn_tool_start=current_turn_tool_start,
        )


class _MismatchedResultBindingRuntime(DeterministicAgenticToolRuntime):
    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        thread_scope_id: str = "",
        current_turn_tool_start: int = 0,
    ) -> AgenticToolExecutionResult:
        return super().execute(
            tool_name=tool_name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            thread_scope_id=thread_scope_id + "-stale",
            current_turn_tool_start=current_turn_tool_start,
        )


def test_tool_dispatch_requires_a_durable_executing_state_ack() -> None:
    runtime = _CountingAgenticToolRuntime()
    loop = _AgenticToolGuardrailLoop(config=_config(), runtime=runtime)

    failed = loop.handle_response(_compute_call("compute-no-checkpoint"))

    assert runtime.execution_count == 0
    assert failed.action == "failed"
    assert failed.failure_reason == "tool_state_checkpoint_failed"
    assert [event.event_type for event in failed.events[-2:]] == [
        "state_checkpoint",
        "terminal_failure",
    ]
    state = loop.state_snapshot()
    assert state["execution_ledger"]["compute-no-checkpoint"]["lifecycle_state"] == (
        "executing"
    )
    assert state["tool_execution_count"] == 1
    assert state["tool_failure_count"] == 0
    assert state["final_outcome"] == "failed"
    assert state["final_failure_reason"] == "tool_state_checkpoint_failed"


def test_runtime_result_binding_mismatch_fails_closed_before_export() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(),
        runtime=_MismatchedResultBindingRuntime(),
    )

    turn = loop.handle_response(_compute_call("compute-stale-binding"))

    assert turn.action == "failed"
    assert turn.tool_results == ()
    assert turn.failure_reason == "tool_result_scope_mismatch"
    assert [event.event_type for event in turn.events[-2:]] == [
        "tool_result_binding",
        "terminal_failure",
    ]


def test_failed_executing_state_ack_prevents_adapter_dispatch() -> None:
    runtime = _CountingAgenticToolRuntime()

    def fail_checkpoint(_state: dict[str, object]) -> None:
        raise OSError("SECRET_CHECKPOINT_FAILURE")

    loop = _AgenticToolGuardrailLoop(
        config=_config(),
        runtime=runtime,
        persist_executing_state=fail_checkpoint,
    )

    failed = loop.handle_response(_compute_call("compute-failed-checkpoint"))

    assert runtime.execution_count == 0
    assert failed.failure_reason == "tool_state_checkpoint_failed"
    assert "SECRET_CHECKPOINT_FAILURE" not in json.dumps(
        [event.as_dict() for event in failed.events]
    )


def test_persisted_executing_state_blocks_replay_after_uncertain_exit() -> None:
    checkpoints: list[dict[str, object]] = []
    first_runtime = _CountingAgenticToolRuntime()
    first_loop = _AgenticToolGuardrailLoop(
        config=_config(),
        runtime=first_runtime,
        persist_executing_state=checkpoints.append,
    )

    completed = first_loop.handle_response(_compute_call("compute-checkpointed"))

    assert completed.action == "finalize"
    assert first_runtime.execution_count == 1
    assert len(checkpoints) == 1
    checkpoint = checkpoints[0]
    assert checkpoint["execution_ledger"]["compute-checkpointed"][
        "lifecycle_state"
    ] == "executing"
    assert checkpoint["tool_execution_count"] == 1
    assert checkpoint["tool_failure_count"] == 0

    replay_runtime = _CountingAgenticToolRuntime()
    replay_loop = _AgenticToolGuardrailLoop(
        config=_config(),
        runtime=replay_runtime,
        state=checkpoint,
        persist_executing_state=_acknowledge_executing_state,
    )
    replay = replay_loop.handle_response(_compute_call("compute-checkpointed"))

    assert replay.action == "failed"
    assert replay.failure_reason == "tool_execution_outcome_uncertain"
    assert replay_runtime.execution_count == 0


def test_persisted_required_execution_blocks_a_fresh_call_identity() -> None:
    checkpoints: list[dict[str, object]] = []
    first_loop = _AgenticToolGuardrailLoop(
        config=_config(),
        runtime=_CountingAgenticToolRuntime(),
        persist_executing_state=checkpoints.append,
    )
    first_loop.handle_response(_compute_call("compute-first-id"))
    restored_runtime = _CountingAgenticToolRuntime()
    restored = _AgenticToolGuardrailLoop(
        config=_config(),
        runtime=restored_runtime,
        state=checkpoints[0],
        persist_executing_state=_acknowledge_executing_state,
    )

    retried = restored.handle_response(_compute_call("compute-fresh-id"))

    assert retried.action == "failed"
    assert retried.failure_reason == "required_tool_execution_outcome_uncertain"
    assert restored_runtime.execution_count == 0


def test_mocked_loop_rescues_text_tool_call_then_accepts_final_answer() -> None:
    responses: Iterable[object] = iter(
        (
            "I should call a tool, but this is not a call.",
            '```json\n{"id":"compute-1","name":"local_compute",'
            '"arguments":{"code":"2 + 2"}}\n```',
            "The answer is 4.",
        )
    )
    observed_nudges: list[str] = []
    observed_tool_results: list[tuple[dict[str, object], ...]] = []

    def respond(directive: object) -> object:
        nudge = getattr(directive, "nudge")
        observed_tool_results.append(getattr(directive, "tool_observations"))
        if nudge is not None:
            observed_nudges.append(str(nudge.kind))
        return next(responses)

    run = run_guarded_agentic_tool_loop(
        respond,
        config=_config(),
        persist_executing_state=_acknowledge_executing_state,
    )

    assert run.outcome == "completed"
    assert run.final_text == "The answer is 4."
    assert observed_nudges == ["premature_terminal", "required_steps_completed"]
    assert observed_tool_results[0] == ()
    assert observed_tool_results[1] == ()
    assert len(observed_tool_results[2]) == 1
    assert observed_tool_results[2][0]["tool_name"] == "local_compute"
    assert run.diagnostics["tool_execution_count"] == 1
    assert run.diagnostics["retry_nudge_count"] == 1
    assert run.turns[1].events[-1].event_type == "model_directive"


def test_unknown_tool_is_rejected_before_execution_then_corrected() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())

    rejected = loop.handle_response(
        {"id": "ghost-1", "name": "ghost_tool", "arguments": {"secret": "DO_NOT_LOG"}}
    )
    corrected = loop.handle_response(_compute_call("compute-1"))

    assert rejected.action == "retry"
    assert rejected.nudge is not None
    assert rejected.nudge.kind == "unknown_tool"
    assert loop.diagnostics()["tool_execution_count"] == 1
    assert corrected.action == "finalize"
    assert "DO_NOT_LOG" not in json.dumps(loop.diagnostics(), sort_keys=True)
    assert "DO_NOT_LOG" not in json.dumps([event.as_dict() for event in rejected.events])


def test_premature_terminal_is_typed_and_exhausts_only_malformed_budget() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(malformed_budget=1, tool_failure_budget=3)
    )

    first = loop.handle_response("I am done early.")
    second = loop.handle_response("Still done early.")

    assert first.action == "retry"
    assert first.nudge is not None
    assert first.nudge.kind == "premature_terminal"
    assert second.action == "failed"
    assert second.failure_reason == "malformed_response_budget_exhausted"
    diagnostics = loop.diagnostics()
    assert diagnostics["consecutive_malformed_responses"] == 2
    assert diagnostics["consecutive_tool_failures"] == 0


def test_default_config_accepts_direct_final_answer_without_required_tools() -> None:
    text_run = run_guarded_agentic_tool_loop(
        lambda directive: "No tool is needed.",
        config=AgenticToolGuardrailConfig(request_id="request-direct-final"),
        persist_executing_state=_acknowledge_executing_state,
    )
    json_run = run_guarded_agentic_tool_loop(
        lambda directive: '{"answer":4}',
        config=AgenticToolGuardrailConfig(request_id="request-direct-json-final"),
        persist_executing_state=_acknowledge_executing_state,
    )

    assert text_run.outcome == "completed"
    assert text_run.final_text == "No tool is needed."
    assert text_run.diagnostics["tool_execution_count"] == 0
    assert text_run.diagnostics["malformed_response_count"] == 0
    assert json_run.outcome == "completed"
    assert json_run.final_text == '{"answer":4}'
    healing_event = next(
        event
        for event in text_run.turns[0].events
        if event.event_type == "healing_decision"
    )
    assert healing_event.outcome == "not_applicable"
    assert healing_event.failure_reason == ""


def test_default_config_does_not_accept_unknown_tool_shape_as_final_text() -> None:
    loop = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(request_id="request-unknown-default")
    )

    rejected = loop.handle_response(
        '```json\n{"id":"unknown-1","name":"ghost_tool","arguments":{}}\n```'
    )

    assert rejected.action == "retry"
    assert rejected.nudge is not None
    assert rejected.nudge.kind == "unknown_tool"
    assert loop.diagnostics()["tool_execution_count"] == 0


def test_pseudo_tool_text_and_empty_response_receive_distinct_malformed_nudges() -> None:
    pseudo_loop = AgenticToolGuardrailLoop(config=_config())
    optional_pseudo_loop = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(request_id="request-optional-pseudo")
    )
    malformed_loop = AgenticToolGuardrailLoop(config=_config())

    pseudo_payload = '{"content":"please run local_compute({\\"code\\":\\"2 + 2\\"})"}'
    pseudo = pseudo_loop.handle_response(pseudo_payload)
    optional_pseudo = optional_pseudo_loop.handle_response(pseudo_payload)
    malformed = malformed_loop.handle_response("")

    assert pseudo.action == "retry"
    assert pseudo.nudge is not None
    assert pseudo.nudge.kind == "pseudo_tool_text_blob"
    assert "not tool-like prose" in pseudo.nudge.message
    assert optional_pseudo.action == "retry"
    assert optional_pseudo.nudge is not None
    assert optional_pseudo.nudge.kind == "pseudo_tool_text_blob"
    assert malformed.action == "retry"
    assert malformed.nudge is not None
    assert malformed.nudge.kind == "malformed_tool_call"


def test_matching_prerequisite_uses_latest_completed_state_in_same_batch() -> None:
    prerequisite = AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )
    loop = AgenticToolGuardrailLoop(
        config=_config(
            required_tools=("text_search", "image_search"),
            prerequisites=(prerequisite,),
        ),
        runtime=DeterministicAgenticToolRuntime(
            fixture_context={"text_corpus": {"default": []}, "image_corpus": {"default": []}}
        ),
    )

    turn = loop.handle_response(
        [
            {"id": "text-1", "name": "text_search", "arguments": {"query": "Melix"}},
            {"id": "image-1", "name": "image_search", "arguments": {"query": "Melix"}},
        ]
    )

    assert turn.action == "finalize"
    assert [result.tool_name for result in turn.tool_results] == ["text_search", "image_search"]
    assert loop.diagnostics()["tool_execution_count"] == 2


def test_batch_retires_remaining_calls_as_soon_as_required_set_completes() -> None:
    loop = AgenticToolGuardrailLoop(config=_config(required_tools=("local_compute",)))

    turn = loop.handle_response(
        [
            _compute_call("required-1", "2 + 2"),
            _compute_call("must-not-run", "3 + 3"),
            _compute_call("also-must-not-run", "4 + 4"),
        ]
    )

    assert turn.action == "finalize"
    assert [result.tool_call_id for result in turn.tool_results] == ["required-1"]
    assert loop.diagnostics()["tool_execution_count"] == 1
    retired = [event for event in turn.events if event.event_type == "tool_call_retired"]
    assert [event.tool_call_id for event in retired] == [
        "must-not-run",
        "also-must-not-run",
    ]
    assert all(event.outcome == "retired" for event in retired)
    assert all(event.failure_reason == "required_steps_completed" for event in retired)


def test_mismatched_prerequisite_is_rejected_without_running_target_tool() -> None:
    prerequisite = AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )
    loop = AgenticToolGuardrailLoop(
        config=_config(
            required_tools=("text_search", "image_search"),
            prerequisites=(prerequisite,),
        ),
        runtime=DeterministicAgenticToolRuntime(
            fixture_context={"text_corpus": {"default": []}, "image_corpus": {"default": []}}
        ),
    )

    first = loop.handle_response(
        {"id": "text-1", "name": "text_search", "arguments": {"query": "Melix"}}
    )
    rejected = loop.handle_response(
        {"id": "image-1", "name": "image_search", "arguments": {"query": "Other"}}
    )

    assert first.action == "continue"
    assert rejected.action == "retry"
    assert rejected.nudge is not None
    assert rejected.nudge.kind == "tool_prerequisite_violation"
    assert loop.diagnostics()["tool_execution_count"] == 1


def test_repeated_prerequisite_rejection_exhausts_malformed_budget() -> None:
    prerequisite = AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )
    loop = AgenticToolGuardrailLoop(
        config=_config(
            required_tools=("text_search", "image_search"),
            prerequisites=(prerequisite,),
            malformed_budget=1,
        ),
        runtime=DeterministicAgenticToolRuntime(
            fixture_context={"text_corpus": {"default": []}, "image_corpus": {"default": []}}
        ),
    )

    first = loop.handle_response(
        {"id": "image-1", "name": "image_search", "arguments": {"query": "Melix"}}
    )
    exhausted = loop.handle_response(
        {"id": "image-2", "name": "image_search", "arguments": {"query": "Melix"}}
    )

    assert first.action == "retry"
    assert exhausted.action == "failed"
    assert exhausted.failure_reason == "malformed_response_budget_exhausted"
    assert loop.diagnostics()["consecutive_malformed_responses"] == 2
    assert loop.diagnostics()["tool_execution_count"] == 0


def test_tool_failure_budget_is_independent_and_success_resets_it() -> None:
    runtime = DeterministicAgenticToolRuntime(
        fixture_context={
            "tool_status_overrides": {
                "fail-1": {"status": "failed"},
                "fail-2": {"status": "timeout"},
                "fail-3": {"status": "failed"},
            }
        }
    )
    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=(), tool_failure_budget=1),
        runtime=runtime,
    )

    first_failure = loop.handle_response(_compute_call("fail-1"))
    success = loop.handle_response(_compute_call("ok-1"))
    second_failure = loop.handle_response(_compute_call("fail-2"))
    exhausted = loop.handle_response(_compute_call("fail-3"))

    assert first_failure.action == "retry"
    assert success.action == "continue"
    assert second_failure.action == "retry"
    assert exhausted.action == "failed"
    assert exhausted.failure_reason == "tool_failure_budget_exhausted"
    diagnostics = loop.diagnostics()
    assert diagnostics["consecutive_malformed_responses"] == 0
    assert diagnostics["tool_failure_count"] == 3


def test_required_tool_failure_terminates_as_uncertain_without_retry_nudge() -> None:
    runtime = DeterministicAgenticToolRuntime(
        fixture_context={"tool_status_overrides": {"fail-required": {"status": "failed"}}}
    )
    loop = AgenticToolGuardrailLoop(config=_config(), runtime=runtime)

    failed = loop.handle_response(_compute_call("fail-required"))

    assert failed.action == "failed"
    assert failed.nudge is None
    assert failed.failure_reason == "required_tool_execution_outcome_uncertain"
    assert loop.diagnostics()["tool_failure_count"] == 1


def test_state_snapshot_survives_message_compaction_and_blocks_missing_step() -> None:
    prerequisite = AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )
    config = _config(
        required_tools=("text_search", "image_search"),
        prerequisites=(prerequisite,),
    )
    fixture = {"text_corpus": {"default": []}, "image_corpus": {"default": []}}
    first_loop = AgenticToolGuardrailLoop(
        config=config,
        runtime=DeterministicAgenticToolRuntime(fixture_context=fixture),
    )
    first_loop.handle_response(
        {"id": "text-1", "name": "text_search", "arguments": {"query": "Melix"}}
    )

    compacted_loop = AgenticToolGuardrailLoop(
        config=config,
        runtime=DeterministicAgenticToolRuntime(fixture_context=fixture),
        state=first_loop.state_snapshot(),
    )
    premature = compacted_loop.handle_response("Done before the image step.")
    admitted = compacted_loop.handle_response(
        {"id": "image-1", "name": "image_search", "arguments": {"query": "Melix"}}
    )

    assert premature.action == "retry"
    assert premature.nudge is not None
    assert premature.nudge.kind == "premature_terminal"
    assert admitted.action == "finalize"
    assert compacted_loop.state_snapshot()["schema_version"] == (
        AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION
    )
    assert compacted_loop.diagnostics()["completed_required_tools"] == [
        "text_search",
        "image_search",
    ]


def test_execution_ledger_suppresses_replay_and_rejects_changed_arguments() -> None:
    loop = AgenticToolGuardrailLoop(config=_config(required_tools=()))

    first = loop.handle_response(_compute_call("compute-1", "2 + 2"))
    replay = loop.handle_response(_compute_call("compute-1", "2 + 2"))
    collision = loop.handle_response(_compute_call("compute-1", "3 + 3"))

    assert first.action == "continue"
    assert first.nudge is not None
    assert first.nudge.kind == "tool_observation_ready"
    assert replay.action == "continue"
    assert replay.tool_results == ()
    assert collision.action == "failed"
    assert collision.failure_reason == "tool_call_identity_conflict"
    diagnostics = loop.diagnostics()
    assert diagnostics["tool_execution_count"] == 1
    assert diagnostics["duplicate_execution_count"] == 0
    assert diagnostics["replay_suppression_count"] == 1


def test_required_tool_lifecycle_is_explicit_and_retires_before_final_answer() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    assert loop.state_snapshot()["required_tool_lifecycle"] == {
        "local_compute": "required"
    }

    turn = loop.handle_response(_compute_call("compute-lifecycle"))
    lifecycle_events = [
        event.outcome
        for event in turn.events
        if event.event_type == "tool_lifecycle"
    ]
    state = loop.state_snapshot()
    ledger = state["execution_ledger"]
    assert isinstance(ledger, dict)
    entry = ledger["compute-lifecycle"]
    assert isinstance(entry, dict)

    assert lifecycle_events == ["authorized", "executing", "completed", "retired"]
    assert state["required_tool_lifecycle"] == {"local_compute": "retired"}
    assert entry["tool_name"] == "local_compute"
    assert entry["lifecycle_state"] == "retired"
    assert isinstance(entry["fingerprint"], str)
    assert len(entry["fingerprint"]) == 64
    assert state["awaiting_final_answer"] is True
    assert loop.next_model_directive().tool_choice == "none"
    assert AgenticToolGuardrailLoop(
        config=_config(), state=state
    ).state_snapshot() == state


def test_completed_required_tool_cannot_execute_again_with_a_new_call_id() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=("local_compute", "text_search")),
        runtime=DeterministicAgenticToolRuntime(
            fixture_context={"text_corpus": {"default": []}}
        ),
    )

    first = loop.handle_response(_compute_call("compute-first"))
    second = loop.handle_response(
        [
            _compute_call("compute-must-not-repeat", "3 + 3"),
            {
                "id": "search-required",
                "name": "text_search",
                "arguments": {"query": "Melix"},
            },
        ]
    )

    assert first.action == "continue"
    assert second.action == "finalize"
    assert [result.tool_call_id for result in second.tool_results] == [
        "search-required"
    ]
    assert loop.diagnostics()["tool_execution_count"] == 2
    retired = [
        event
        for event in second.events
        if event.event_type == "tool_call_retired"
        and event.failure_reason == "required_step_already_completed"
    ]
    assert [event.tool_call_id for event in retired] == [
        "compute-must-not-repeat"
    ]
    state = loop.state_snapshot()
    assert "compute-must-not-repeat" not in state["execution_ledger"]
    assert state["required_tool_lifecycle"] == {
        "local_compute": "retired",
        "text_search": "retired",
    }


def test_admitted_exact_replay_does_not_reset_malformed_response_budget() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=(), malformed_budget=1)
    )
    loop.handle_response(_compute_call("compute-replay"))
    first_malformed = loop.handle_response(
        {"id": "unknown-1", "name": "ghost_tool", "arguments": {}}
    )

    replay = loop.handle_response(_compute_call("compute-replay"))
    second_malformed = loop.handle_response(
        {"id": "unknown-2", "name": "ghost_tool", "arguments": {}}
    )

    assert first_malformed.action == "retry"
    assert replay.action == "continue"
    assert any(event.event_type == "replay_suppressed" for event in replay.events)
    assert second_malformed.action == "failed"
    assert second_malformed.failure_reason == "malformed_response_budget_exhausted"
    assert loop.diagnostics()["consecutive_malformed_responses"] == 2


def test_exhaust_turn_budget_is_idempotent_after_completion() -> None:
    loop = AgenticToolGuardrailLoop(config=_config(required_tools=()))
    completed = loop.handle_response("final answer")
    state = loop.state_snapshot()

    exhausted = loop.exhaust_turn_budget()

    assert completed.action == "complete"
    assert exhausted.action == "complete"
    assert exhausted.events == ()
    assert loop.state_snapshot() == state


def test_exhaust_turn_budget_is_idempotent_after_failure() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=(), malformed_budget=0)
    )
    failed = loop.handle_response(
        {"id": "unknown", "name": "ghost_tool", "arguments": {}}
    )
    state = loop.state_snapshot()

    exhausted = loop.exhaust_turn_budget()

    assert failed.action == "failed"
    assert exhausted.action == "failed"
    assert exhausted.failure_reason == "malformed_response_budget_exhausted"
    assert exhausted.events == ()
    assert loop.state_snapshot() == state


def test_adapter_exception_emits_sanitized_tool_execution_error_event() -> None:
    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=()),
        runtime=_RaisingAgenticToolRuntime(),
    )

    turn = loop.handle_response(
        _compute_call("adapter-error", "2 + 2 # SECRET_ARGUMENT")
    )

    execution_event = next(
        event for event in turn.events if event.event_type == "tool_execution"
    )
    assert turn.action == "retry"
    assert execution_event.outcome == "adapter_error"
    assert execution_event.failure_reason == "tool_adapter_error"
    assert loop.diagnostics()["tool_execution_count"] == 1
    assert loop.diagnostics()["tool_failure_count"] == 1
    serialized = json.dumps([event.as_dict() for event in turn.events], sort_keys=True)
    assert "SECRET_ADAPTER_EXCEPTION" not in serialized
    assert "SECRET_ARGUMENT" not in serialized
    assert "arguments" not in serialized


def test_tool_execution_is_retired_after_required_steps_complete() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    loop.handle_response(_compute_call("compute-1"))

    retired = loop.handle_response(_compute_call("compute-2"))

    assert retired.action == "retry"
    assert retired.nudge is not None
    assert retired.nudge.kind == "tools_retired"
    assert loop.diagnostics()["tool_execution_count"] == 1


@pytest.mark.parametrize(
    "pseudo_final",
    (
        'please run local_compute({"code":"3 + 3"})',
        '{"content":"please run local_compute({\\"code\\":\\"3 + 3\\"})"}',
        '{"id":"unknown-final","name":"ghost_tool","arguments":{}}',
    ),
)
def test_final_answer_stage_rejects_pseudo_tool_and_receipt_shapes(
    pseudo_final: str,
) -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    loop.handle_response(_compute_call("compute-final-stage"))

    rejected = loop.handle_response(pseudo_final)

    assert rejected.action == "retry"
    assert rejected.nudge is not None
    assert rejected.nudge.kind == "tools_retired"
    assert loop.diagnostics()["final_outcome"] == "running"
    assert loop.diagnostics()["tool_execution_count"] == 1


def test_final_answer_stage_allows_plain_tool_result_explanation() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    loop.handle_response(_compute_call("compute-final-explanation"))

    completed = loop.handle_response("local_compute returned 4.")

    assert completed.action == "complete"
    assert completed.final_text == "local_compute returned 4."


def test_stream_delta_adapter_preserves_calls_and_invalid_argument_shapes() -> None:
    deltas = (
        AssemblyDelta(
            tool_call=AssembledToolCall(
                call_id="compute-1",
                tool_name="local_compute",
                arguments_json_fragment='{"code":"2 + 2"}',
                fragment_index=0,
                parser_mode="qwen",
            )
        ),
        AssemblyDelta(
            tool_call=AssembledToolCall(
                call_id="compute-2",
                tool_name="local_compute",
                arguments_json_fragment='["not-an-object"]',
                fragment_index=1,
                parser_mode="qwen",
            )
        ),
    )

    calls = agentic_tool_calls_from_stream_deltas(deltas)

    assert calls == (
        _compute_call("compute-1"),
        {"id": "compute-2", "name": "local_compute", "arguments": ["not-an-object"]},
    )


def test_diagnostics_and_events_are_versioned_and_never_include_raw_arguments() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    turn = loop.handle_response(_compute_call("compute-secret", "SECRET_VALUE + 1"))
    diagnostics = loop.diagnostics()

    assert diagnostics["schema_version"] == AGENTIC_TOOL_GUARDRAIL_DIAGNOSTIC_SCHEMA_VERSION
    assert all(
        event.as_dict()["schema_version"] == AGENTIC_TOOL_GUARDRAIL_EVENT_SCHEMA_VERSION
        for event in turn.events
    )
    serialized = json.dumps(
        {"diagnostics": diagnostics, "events": [event.as_dict() for event in turn.events]},
        sort_keys=True,
    )
    assert "SECRET_VALUE" not in serialized
    assert "arguments" not in serialized


@pytest.mark.parametrize(
    "kwargs",
    (
        {"request_id": ""},
        {"request_id": "request-1", "thread_scope_id": " "},
        {"request_id": "request-1", "current_turn_tool_start": -1},
        {"request_id": "request-1", "tool_result_export_policy": "ui_full"},
        {"request_id": "request-1", "max_consecutive_malformed_responses": -1},
        {"request_id": "request-1", "max_consecutive_tool_failures": -1},
        {"request_id": "request-1", "max_turns": 0},
    ),
)
def test_config_rejects_invalid_budgets_and_identity(kwargs: dict[str, object]) -> None:
    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailConfig(**kwargs)  # type: ignore[arg-type]


def test_config_and_nudge_have_serializable_control_plane_shapes() -> None:
    prerequisite = AgenticToolPrerequisite(
        tool_name="image_search",
        required_tool_name="text_search",
        argument_match_keys=("query",),
    )
    config = _config(prerequisites=(prerequisite,))
    loop = AgenticToolGuardrailLoop(config=config)
    turn = loop.handle_response("too soon")

    assert config.as_dict()["schema_version"] == AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION
    assert config.as_dict()["prerequisites"] == [
        {
            "tool_name": "image_search",
            "required_tool_name": "text_search",
            "argument_match_keys": ["query"],
        }
    ]
    assert turn.nudge is not None
    assert turn.nudge.as_dict()["kind"] == "premature_terminal"
    directive = loop.next_model_directive(turn.nudge)
    assert directive.tool_choice == "required"
    assert directive.context_messages == (
        {"role": "system", "content": turn.nudge.message},
    )


def test_swift_execution_metadata_round_trips_config_and_restorable_state() -> None:
    config = _config()
    state = AgenticToolGuardrailLoop(config=config).state_snapshot()
    ext = {
        "melix.agentic_guardrail.config_schema": AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION,
        "melix.agentic_guardrail.config_json": json.dumps(config.as_dict()),
        "melix.agentic_guardrail.state_schema": AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION,
        "melix.agentic_guardrail.state_json": json.dumps(state),
    }

    restored_config, restored_state = agentic_tool_guardrail_inputs_from_execution_ext(ext)

    assert restored_config == config
    assert restored_state == state
    assert AgenticToolGuardrailLoop(
        config=restored_config,
        state=restored_state,
    ).state_snapshot() == state
    config_only, absent_state = agentic_tool_guardrail_inputs_from_execution_ext(
        {
            "melix.agentic_guardrail.config_schema": (
                AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION
            ),
            "melix.agentic_guardrail.config_json": json.dumps(config.as_dict()),
        }
    )
    assert config_only == config
    assert absent_state is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", "future"),
        ("request_id", None),
        ("required_tools", "local_compute"),
        ("prerequisites", "not-a-list"),
        ("prerequisites", ["not-an-object"]),
        (
            "prerequisites",
            [
                {
                    "tool_name": "",
                    "required_tool_name": "text_search",
                    "argument_match_keys": [],
                }
            ],
        ),
        (
            "prerequisites",
            [
                {
                    "tool_name": "image_search",
                    "required_tool_name": "text_search",
                    "argument_match_keys": "query",
                }
            ],
        ),
        ("max_consecutive_tool_failures", True),
    ),
)
def test_config_decoder_rejects_invalid_swift_contract_fields(
    field: str,
    value: object,
) -> None:
    payload = _config().as_dict()
    payload[field] = value

    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailConfig.from_dict(payload)


def _replace_ext_state_field(
    ext: dict[str, str],
    field: str,
    value: object,
) -> None:
    payload = json.loads(ext["melix.agentic_guardrail.state_json"])
    payload[field] = value
    ext["melix.agentic_guardrail.state_json"] = json.dumps(payload)


@pytest.mark.parametrize(
    "mutate_ext",
    (
        lambda ext: ext.pop("melix.agentic_guardrail.config_schema"),
        lambda ext: ext.pop("melix.agentic_guardrail.config_json"),
        lambda ext: ext.__setitem__("melix.agentic_guardrail.config_json", "[]"),
        lambda ext: ext.__setitem__("melix.agentic_guardrail.config_json", "{"),
        lambda ext: ext.__setitem__("melix.agentic_guardrail.state_schema", "future"),
        lambda ext: ext.pop("melix.agentic_guardrail.state_json"),
        lambda ext: ext.__setitem__("melix.agentic_guardrail.state_json", "[]"),
        lambda ext: ext.__setitem__(
            "melix.agentic_guardrail.state_json",
            ext["melix.agentic_guardrail.state_json"].replace(
                AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION,
                "future",
            ),
        ),
        lambda ext: ext.__setitem__(
            "melix.agentic_guardrail.state_json",
            ext["melix.agentic_guardrail.state_json"].replace(
                "request-guardrail-test",
                "another-request",
            ),
        ),
        lambda ext: _replace_ext_state_field(ext, "responses_seen", -1),
        lambda ext: _replace_ext_state_field(ext, "terminal", "false"),
        lambda ext: _replace_ext_state_field(ext, "final_outcome", "future"),
    ),
)
def test_worker_execution_metadata_rejects_invalid_contract(
    mutate_ext: Callable[[dict[str, str]], object],
) -> None:
    config = _config()
    ext = {
        "melix.agentic_guardrail.config_schema": AGENTIC_TOOL_GUARDRAIL_CONFIG_SCHEMA_VERSION,
        "melix.agentic_guardrail.config_json": json.dumps(config.as_dict()),
        "melix.agentic_guardrail.state_schema": AGENTIC_TOOL_GUARDRAIL_STATE_SCHEMA_VERSION,
        "melix.agentic_guardrail.state_json": json.dumps(
            AgenticToolGuardrailLoop(config=config).state_snapshot()
        ),
    }
    mutate_ext(ext)

    with pytest.raises(AgenticToolGuardrailLoopError):
        agentic_tool_guardrail_inputs_from_execution_ext(ext)


def test_terminal_loop_ignores_later_responses_and_runner_exhausts_turn_budget() -> None:
    completed = AgenticToolGuardrailLoop(config=_config())
    completed.handle_response(_compute_call("compute-1"))
    completed.handle_response("done")

    ignored = completed.handle_response("later")
    exhausted = run_guarded_agentic_tool_loop(
        lambda _directive: "still too soon",
        config=AgenticToolGuardrailConfig(
            request_id="request-turn-budget",
            required_tools=("local_compute",),
            max_consecutive_malformed_responses=5,
            max_turns=1,
        ),
        persist_executing_state=_acknowledge_executing_state,
    )

    assert ignored.action == "complete"
    assert ignored.events[0].event_type == "response_ignored"
    assert exhausted.outcome == "failed"
    assert exhausted.diagnostics["final_failure_reason"] == "turn_budget_exhausted"


def test_turn_budget_is_cumulative_across_restored_runner_state() -> None:
    config = AgenticToolGuardrailConfig(
        request_id="request-restored-turn-budget",
        required_tools=("local_compute",),
        max_consecutive_malformed_responses=5,
        max_turns=2,
    )
    first_loop = AgenticToolGuardrailLoop(config=config)
    first_loop.handle_response("first premature answer")
    responder_calls = 0

    def respond(_directive: object) -> object:
        nonlocal responder_calls
        responder_calls += 1
        return "second premature answer"

    run = run_guarded_agentic_tool_loop(
        respond,
        config=config,
        state=first_loop.state_snapshot(),
        persist_executing_state=_acknowledge_executing_state,
    )
    restored_terminal = run_guarded_agentic_tool_loop(
        lambda _directive: pytest.fail("terminal restore must not call responder"),
        config=config,
        state=run.state,
        persist_executing_state=_acknowledge_executing_state,
    )

    assert responder_calls == 1
    assert run.outcome == "failed"
    assert run.diagnostics["responses_seen"] == 2
    assert run.diagnostics["final_failure_reason"] == "turn_budget_exhausted"
    assert restored_terminal.outcome == "failed"
    assert restored_terminal.turns == ()


def test_empty_final_response_and_non_json_stream_arguments_are_typed() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    loop.handle_response(_compute_call("compute-1"))

    empty = loop.handle_response("  ")
    calls = agentic_tool_calls_from_stream_deltas(
        (
            AssemblyDelta(content_text="ordinary text"),
            AssemblyDelta(
                tool_call=AssembledToolCall(
                    call_id="compute-invalid",
                    tool_name="local_compute",
                    arguments_json_fragment="not-json",
                    fragment_index=0,
                    parser_mode="qwen",
                )
            ),
        )
    )

    assert empty.action == "retry"
    assert empty.nudge is not None
    assert empty.nudge.kind == "final_response_required"
    assert calls[0]["arguments"] == "not-json"


def test_state_restore_rejects_wrong_schema_request_and_missing_fields() -> None:
    config = _config()
    state = AgenticToolGuardrailLoop(config=config).state_snapshot()
    invalid_states = (
        {**state, "schema_version": "future"},
        {**state, "request_id": "another-request"},
        {key: value for key, value in state.items() if key != "execution_ledger"},
    )

    for invalid_state in invalid_states:
        with pytest.raises(AgenticToolGuardrailLoopError):
            AgenticToolGuardrailLoop(config=config, state=invalid_state)
    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailLoop(config=config, state=[])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    (
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
    ),
)
def test_state_restore_rejects_negative_and_boolean_counters(field: str) -> None:
    config = _config()
    state = AgenticToolGuardrailLoop(config=config).state_snapshot()

    for invalid_value in (-1, True):
        invalid_state = {**state, field: invalid_value}
        with pytest.raises(AgenticToolGuardrailLoopError):
            AgenticToolGuardrailLoop(config=config, state=invalid_state)


@pytest.mark.parametrize(
    "mutate_state",
    (
        lambda state: state.__setitem__("terminal", "false"),
        lambda state: state.__setitem__("awaiting_final_answer", 0),
        lambda state: state.__setitem__("preflight_event_emitted", "false"),
        lambda state: state.__setitem__("last_nudge_type", None),
        lambda state: state.__setitem__("thread_scope_id", None),
        lambda state: state.__setitem__("current_turn_tool_start", False),
        lambda state: state.__setitem__("tool_result_export_policy", None),
        lambda state: state.__setitem__("final_outcome", "future"),
        lambda state: state.__setitem__("final_failure_reason", []),
        lambda state: state.__setitem__("completed_tool_calls", {}),
        lambda state: state.__setitem__("execution_ledger", []),
        lambda state: state.__setitem__("required_tool_lifecycle", []),
        lambda state: state.__setitem__("responses_seen", 13),
        lambda state: state.__setitem__("terminal", True),
        lambda state: state.update({"final_outcome": "completed", "terminal": False}),
        lambda state: state.update(
            {
                "final_outcome": "failed",
                "terminal": True,
                "final_failure_reason": "",
                "terminal_failure_count": 1,
            }
        ),
        lambda state: state.__setitem__("awaiting_final_answer", True),
        lambda state: state.update(
            {"preflight_event_emitted": True, "event_sequence": 0}
        ),
        lambda state: state.__setitem__("unexpected_v1_field", 1),
    ),
)
def test_state_restore_rejects_wrong_types_and_inconsistent_outcomes(
    mutate_state: Callable[[dict[str, object]], object],
) -> None:
    config = _config()
    state = AgenticToolGuardrailLoop(config=config).state_snapshot()
    mutate_state(state)

    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailLoop(config=config, state=state)


@pytest.mark.parametrize(
    "mutate_state",
    (
        lambda state: state.__setitem__("tool_execution_count", 0),
        lambda state: state["execution_ledger"].__setitem__(  # type: ignore[union-attr]
            "compute-state", "0" * 64
        ),
        lambda state: state["completed_tool_calls"][0].__setitem__(  # type: ignore[index,union-attr]
            "arguments", {"code": float("nan")}
        ),
        lambda state: state["completed_tool_calls"].append(  # type: ignore[union-attr]
            state["completed_tool_calls"][0]  # type: ignore[index]
        ),
    ),
)
def test_state_restore_rejects_forged_execution_evidence(
    mutate_state: Callable[[dict[str, object]], object],
) -> None:
    config = _config(required_tools=())
    loop = AgenticToolGuardrailLoop(config=config)
    loop.handle_response(_compute_call("compute-state"))
    state = loop.state_snapshot()
    mutate_state(state)

    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailLoop(config=config, state=state)


def test_checkpoint_callback_cannot_mutate_live_guardrail_state() -> None:
    checkpoint_snapshots: list[dict[str, object]] = []

    def mutate_checkpoint(snapshot: dict[str, object]) -> None:
        checkpoint_snapshots.append(snapshot)
        snapshot["completed_tool_calls"].clear()  # type: ignore[union-attr]
        snapshot["execution_ledger"].clear()  # type: ignore[union-attr]

    loop = AgenticToolGuardrailLoop(
        config=_config(required_tools=()),
        persist_executing_state=mutate_checkpoint,
    )

    loop.handle_response(_compute_call("compute-checkpoint-a"))
    loop.handle_response(_compute_call("compute-checkpoint-b"))

    state = loop.state_snapshot()
    assert len(checkpoint_snapshots) == 2
    assert [call["id"] for call in state["completed_tool_calls"]] == [  # type: ignore[index]
        "compute-checkpoint-a",
        "compute-checkpoint-b",
    ]
    assert set(state["execution_ledger"]) == {  # type: ignore[arg-type]
        "compute-checkpoint-a",
        "compute-checkpoint-b",
    }


def test_state_snapshot_json_copy_isolates_nested_containers() -> None:
    source = {"items": [{"value": 1}]}

    copied = _copy_json_value(source)
    copied["items"][0]["value"] = 2

    assert source == {"items": [{"value": 1}]}


@pytest.mark.parametrize(
    "mutate_state",
    (
        lambda state: state["required_tool_lifecycle"].__setitem__(  # type: ignore[union-attr]
            "local_compute", "required"
        ),
        lambda state: state["required_tool_lifecycle"].__setitem__(  # type: ignore[union-attr]
            "ghost_tool", "required"
        ),
        lambda state: state["execution_ledger"]["compute-lifecycle"].__setitem__(  # type: ignore[index,union-attr]
            "lifecycle_state", "future"
        ),
        lambda state: state["execution_ledger"]["compute-lifecycle"].__setitem__(  # type: ignore[index,union-attr]
            "tool_name", "ghost_tool"
        ),
    ),
)
def test_state_restore_rejects_forged_required_tool_lifecycle(
    mutate_state: Callable[[dict[str, object]], object],
) -> None:
    config = _config()
    loop = AgenticToolGuardrailLoop(config=config)
    loop.handle_response(_compute_call("compute-lifecycle"))
    state = loop.state_snapshot()
    mutate_state(state)

    with pytest.raises(AgenticToolGuardrailLoopError):
        AgenticToolGuardrailLoop(config=config, state=state)


def test_state_restore_rejects_required_tool_lifecycle_shadow_entry() -> None:
    config = _config()
    loop = AgenticToolGuardrailLoop(config=config)
    loop.handle_response(_compute_call("compute-lifecycle"))
    state = loop.state_snapshot()
    state["execution_ledger"]["authorized-shadow"] = {  # type: ignore[index]
        "fingerprint": "1" * 64,
        "tool_name": "local_compute",
        "lifecycle_state": "authorized",
    }
    state["required_tool_lifecycle"]["local_compute"] = "authorized"  # type: ignore[index]

    with pytest.raises(
        AgenticToolGuardrailLoopError,
        match="uniquely match execution-ledger evidence",
    ):
        AgenticToolGuardrailLoop(config=config, state=state)


def test_completed_state_clears_awaiting_final_and_restores_consistently() -> None:
    config = _config()
    loop = AgenticToolGuardrailLoop(config=config)
    loop.handle_response(_compute_call("compute-complete"))
    loop.handle_response("done")
    state = loop.state_snapshot()

    restored = AgenticToolGuardrailLoop(config=config, state=state)

    assert state["final_outcome"] == "completed"
    assert state["terminal"] is True
    assert state["awaiting_final_answer"] is False
    assert restored.state_snapshot() == state


def test_completed_restore_requires_configured_required_steps() -> None:
    config = _config()
    state = AgenticToolGuardrailLoop(config=config).state_snapshot()
    state.update(
        {
            "responses_seen": 1,
            "preflight_event_emitted": True,
            "event_sequence": 2,
            "final_outcome": "completed",
            "terminal": True,
        }
    )

    with pytest.raises(AgenticToolGuardrailLoopError, match="required steps"):
        AgenticToolGuardrailLoop(config=config, state=state)


def test_restore_accepts_only_matching_terminal_budget_exhaustion() -> None:
    malformed_config = _config(malformed_budget=1)
    malformed_loop = AgenticToolGuardrailLoop(config=malformed_config)
    malformed_loop.handle_response("too soon")
    malformed_loop.handle_response("still too soon")
    malformed_state = malformed_loop.state_snapshot()

    tool_config = _config(required_tools=(), tool_failure_budget=1)
    tool_loop = AgenticToolGuardrailLoop(
        config=tool_config,
        runtime=DeterministicAgenticToolRuntime(
            fixture_context={
                "tool_status_overrides": {
                    "fail-1": {"status": "failed"},
                    "fail-2": {"status": "failed"},
                }
            }
        ),
    )
    tool_loop.handle_response(_compute_call("fail-1"))
    tool_loop.handle_response(_compute_call("fail-2"))
    tool_state = tool_loop.state_snapshot()

    AgenticToolGuardrailLoop(config=malformed_config, state=malformed_state)
    AgenticToolGuardrailLoop(config=tool_config, state=tool_state)

    for config, state in (
        (malformed_config, malformed_state),
        (tool_config, tool_state),
    ):
        forged_running = {
            **state,
            "final_outcome": "running",
            "final_failure_reason": "",
            "terminal": False,
            "terminal_failure_count": 0,
        }
        with pytest.raises(AgenticToolGuardrailLoopError, match="over-budget"):
            AgenticToolGuardrailLoop(config=config, state=forged_running)

    malformed_state["consecutive_malformed_responses"] = 1
    with pytest.raises(AgenticToolGuardrailLoopError, match="exact over-budget"):
        AgenticToolGuardrailLoop(config=malformed_config, state=malformed_state)


def test_restore_rejects_terminal_states_without_operational_evidence() -> None:
    config = _config(required_tools=())
    initial_state = AgenticToolGuardrailLoop(config=config).state_snapshot()
    completed_without_response = {
        **initial_state,
        "preflight_event_emitted": True,
        "event_sequence": 1,
        "final_outcome": "completed",
        "terminal": True,
    }
    failed_without_preflight = {
        **initial_state,
        "final_outcome": "failed",
        "final_failure_reason": "tool_call_identity_conflict",
        "terminal": True,
        "terminal_failure_count": 1,
    }

    with pytest.raises(AgenticToolGuardrailLoopError, match="model response"):
        AgenticToolGuardrailLoop(config=config, state=completed_without_response)
    with pytest.raises(AgenticToolGuardrailLoopError, match="preflight evidence"):
        AgenticToolGuardrailLoop(config=config, state=failed_without_preflight)


@pytest.mark.parametrize(
    "invalid_value",
    (
        {"not-json-serializable"},
        ("tuple-is-not-a-v1-array",),
        float("nan"),
    ),
    ids=("set", "tuple", "nan"),
)
def test_non_v1_json_argument_value_is_rejected_before_adapter_dispatch(
    invalid_value: object,
) -> None:
    runtime = _CountingAgenticToolRuntime()
    loop = AgenticToolGuardrailLoop(config=_config(), runtime=runtime)

    rejected = loop.handle_response(
        {
            "id": "compute-invalid-json",
            "name": "local_compute",
            "arguments": {"code": invalid_value},
        }
    )

    assert rejected.action == "retry"
    assert rejected.nudge is not None
    assert rejected.nudge.kind == "invalid_arguments"
    assert runtime.execution_count == 0
    assert loop.diagnostics()["tool_execution_count"] == 0


def test_model_directive_retires_tools_without_exposing_control_state() -> None:
    loop = AgenticToolGuardrailLoop(config=_config())
    initial = loop.next_model_directive()
    completed = loop.handle_response(
        _compute_call("compute-secret", "2 + 2 # SECRET_CONTROL_STATE")
    )
    final = loop.next_model_directive(completed.nudge)

    assert initial.tool_choice == "required"
    assert initial.context_messages == ()
    assert final.tool_choice == "none"
    assert "SECRET_CONTROL_STATE" not in json.dumps(final.context_messages)


def test_model_directive_keeps_only_current_observation_as_ledger_grows() -> None:
    turn_count = 64
    loop = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="request-prompt-growth",
            max_turns=turn_count + 1,
        )
    )
    directive_sizes: list[int] = []

    for index in range(turn_count):
        turn = loop.handle_response(
            _compute_call(f"prompt-call-{index:06d}", "1 + 1")
        )
        directive = loop.next_model_directive(
            turn.nudge, tool_observations=turn.tool_results
        )
        assert len(directive.context_messages) == 1
        assert len(directive.tool_observations) == 1
        directive_sizes.append(
            len(
                json.dumps(
                    {
                        "context_messages": directive.context_messages,
                        "tool_observations": directive.tool_observations,
                    },
                    sort_keys=True,
                )
            )
        )

    state = loop.state_snapshot()
    assert len(state["execution_ledger"]) == turn_count  # type: ignore[arg-type]
    first_half = sum(directive_sizes[: turn_count // 2])
    second_half = sum(directive_sizes[turn_count // 2 :])
    assert second_half / first_half <= 1.01


def test_thread_and_turn_boundaries_reject_cross_scope_state_restore() -> None:
    runtime = _ThreadScopedAgenticToolRuntime()
    first_config = AgenticToolGuardrailConfig(
        request_id="request-thread-a",
        thread_scope_id="thread-a",
        current_turn_tool_start=7,
    )
    first = AgenticToolGuardrailLoop(config=first_config, runtime=runtime)
    first.handle_response(_compute_call("thread-a-call"))
    second = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="request-thread-b",
            thread_scope_id="thread-b",
            current_turn_tool_start=7,
        ),
        runtime=runtime,
    )
    second.handle_response(_compute_call("thread-b-call"))

    assert runtime.session_execution_counts == {"thread-a": 1, "thread-b": 1}

    state = first.state_snapshot()
    state["request_id"] = "request-thread-b"
    with pytest.raises(AgenticToolGuardrailLoopError, match="boundary"):
        AgenticToolGuardrailLoop(
            config=AgenticToolGuardrailConfig(
                request_id="request-thread-b",
                thread_scope_id="thread-b",
                current_turn_tool_start=7,
            ),
            state=state,
        )
    state["thread_scope_id"] = "thread-b"
    with pytest.raises(AgenticToolGuardrailLoopError, match="boundary"):
        AgenticToolGuardrailLoop(
            config=AgenticToolGuardrailConfig(
                request_id="request-thread-b",
                thread_scope_id="thread-b",
                current_turn_tool_start=8,
            ),
            state=state,
        )


@pytest.mark.parametrize(
    ("thread_scope_id", "current_turn_tool_start"),
    [("thread-b", 7), ("thread-a", 8)],
)
def test_model_directive_rejects_tool_results_from_another_thread_or_turn(
    thread_scope_id: str,
    current_turn_tool_start: int,
) -> None:
    source = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="request-thread-a",
            thread_scope_id="thread-a",
            current_turn_tool_start=7,
        )
    )
    source_turn = source.handle_response(_compute_call("thread-a-export"))
    target = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="request-target",
            thread_scope_id=thread_scope_id,
            current_turn_tool_start=current_turn_tool_start,
        )
    )

    with pytest.raises(AgenticToolGuardrailLoopError, match="boundary") as caught:
        target.next_model_directive(tool_observations=source_turn.tool_results)

    assert caught.value.event is not None
    assert caught.value.event.event_type == "tool_result_export"
    assert caught.value.event.outcome == "rejected"
    assert caught.value.event.failure_reason == "tool_result_scope_mismatch"


def test_model_directive_exports_text_summary_without_frontend_media_envelope() -> None:
    config = AgenticToolGuardrailConfig(
        request_id="request-media-export",
        thread_scope_id="thread-media",
        current_turn_tool_start=4,
        required_tools=("image_crop",),
    )
    loop = AgenticToolGuardrailLoop(
        config=config,
        runtime=_ImageEnvelopeAgenticToolRuntime(),
    )
    turn = loop.handle_response(
        {
            "id": "image-call",
            "name": "image_crop",
            "arguments": {"media_ref": "receipt-42", "region": "total"},
        }
    )
    directive = loop.next_model_directive(
        turn.nudge,
        tool_observations=turn.tool_results,
    )

    operator_payload = turn.tool_results[0].observation.payload
    assert "PRIVATE_IMAGE_BYTES" in str(operator_payload["image_data"])
    serialized_model_payload = json.dumps(directive.tool_observations, sort_keys=True)
    assert "receipt total is 42" in serialized_model_payload
    assert "PRIVATE_IMAGE_BYTES" not in serialized_model_payload
    assert "NESTED_PRIVATE_BYTES" not in serialized_model_payload
    assert "INLINE_PRIVATE_BYTES" not in serialized_model_payload
    assert "image_data" not in serialized_model_payload
    assert "<tool_result>" not in serialized_model_payload
    text_summary = directive.tool_observations[0]["text_summary"]
    assert isinstance(text_summary, str)
    projected_summary = json.loads(text_summary)
    assert "frontend_payload" not in projected_summary["details"]
    assert projected_summary["details"]["line_count"] == 3
    assert projected_summary["details"]["ratio"] == 1.5
    assert directive.tool_observations[0]["thread_scope_id"] == "thread-media"
    assert directive.tool_observations[0]["current_turn_tool_start"] == 4
    assert all(event.thread_scope_id == "thread-media" for event in turn.events)


def test_model_directive_preserves_real_structured_runtime_results() -> None:
    cases = (
        (
            "local_compute",
            {"code": "2 + 2"},
            {},
            lambda payload: payload["result"] == 4,
        ),
        (
            "text_search",
            {"query": "Melix"},
            {
                "text_corpus": [
                    {"id": "doc-1", "text": "Melix keeps structured search output."}
                ]
            },
            lambda payload: payload["results"] == [
                {"id": "doc-1", "text": "Melix keeps structured search output."}
            ],
        ),
        (
            "layout_parse",
            {"media_ref": "receipt-layout"},
            {
                "layouts": {
                    "receipt-layout": [
                        {"kind": "text", "text": "Total: 42"}
                    ]
                }
            },
            lambda payload: payload["elements"] == [
                {"kind": "text", "text": "Total: 42"}
            ],
        ),
    )

    for index, (tool_name, arguments, fixture_context, assertion) in enumerate(cases):
        loop = AgenticToolGuardrailLoop(
            config=AgenticToolGuardrailConfig(
                request_id=f"request-structured-{index}",
                required_tools=(tool_name,),
            ),
            runtime=DeterministicAgenticToolRuntime(fixture_context=fixture_context),
        )
        turn = loop.handle_response(
            {
                "id": f"structured-{index}",
                "name": tool_name,
                "arguments": arguments,
            }
        )
        directive = loop.next_model_directive(
            turn.nudge,
            tool_observations=turn.tool_results,
        )
        text_summary = directive.tool_observations[0]["text_summary"]
        assert isinstance(text_summary, str)
        assert len(text_summary.encode("utf-8")) <= 8192
        assert assertion(json.loads(text_summary))


def test_model_directive_bounds_large_structured_result_as_valid_json_preview() -> None:
    runtime = DeterministicAgenticToolRuntime(
        fixture_context={
            "text_corpus": [
                {
                    "id": f"doc-{index}",
                    "text": "Melix essential result 42 " + ("x" * 2_000),
                }
                for index in range(8)
            ]
        }
    )
    loop = AgenticToolGuardrailLoop(
        config=AgenticToolGuardrailConfig(
            request_id="request-large-structured",
            required_tools=("text_search",),
        ),
        runtime=runtime,
    )
    turn = loop.handle_response(
        {
            "id": "large-search",
            "name": "text_search",
            "arguments": {"query": "Melix", "max_results": 8},
        }
    )

    directive = loop.next_model_directive(
        turn.nudge,
        tool_observations=turn.tool_results,
    )
    text_summary = directive.tool_observations[0]["text_summary"]

    assert isinstance(text_summary, str)
    assert len(text_summary.encode("utf-8")) <= 8192
    preview = json.loads(text_summary)
    assert preview["truncated"] is True
    assert "Melix essential result 42" in preview["json_preview"]


def test_successful_selected_registry_preflight_emits_once_across_restore() -> None:
    config = _config()
    loop = AgenticToolGuardrailLoop(config=config)
    first = loop.handle_response("too soon")
    restored = AgenticToolGuardrailLoop(config=config, state=loop.state_snapshot())
    second = restored.handle_response("still too soon")

    assert first.events[0].event_type == "guardrail_preflight"
    assert first.events[0].outcome == "passed"
    assert all(event.event_type != "guardrail_preflight" for event in second.events)


def test_loop_rejects_required_tool_outside_selected_registry() -> None:
    with pytest.raises(AgenticToolGuardrailLoopError, match="ghost_tool") as caught:
        AgenticToolGuardrailLoop(
            config=AgenticToolGuardrailConfig(
                request_id="request-unknown-required",
                required_tools=("ghost_tool",),
            )
        )
    event = caught.value.event
    assert event is not None
    assert event.event_type == "guardrail_preflight"
    assert event.outcome == "rejected"
    assert event.failure_reason == "configured_tool_unavailable"
    assert event.tool_name == "ghost_tool"
    assert event.thread_scope_id == "request-unknown-required"
    assert event.current_turn_tool_start == 0
    assert event.tool_result_export_policy == "model_text_summary_ui_full"


@pytest.mark.parametrize(
    "prerequisite",
    (
        AgenticToolPrerequisite(
            tool_name="ghost_target",
            required_tool_name="local_compute",
        ),
        AgenticToolPrerequisite(
            tool_name="local_compute",
            required_tool_name="ghost_required",
        ),
    ),
)
def test_loop_rejects_prerequisite_endpoints_outside_selected_registry(
    prerequisite: AgenticToolPrerequisite,
) -> None:
    with pytest.raises(AgenticToolGuardrailLoopError) as caught:
        AgenticToolGuardrailLoop(
            config=_config(prerequisites=(prerequisite,)),
        )

    assert caught.value.event is not None
    assert caught.value.event.event_type == "guardrail_preflight"
    assert caught.value.event.outcome == "rejected"
