from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

import pytest

from packages.protocol.python.computer.v1 import computer_pb2
from packages.protocol.python.worker.v1 import tool_runtime_pb2
from worker.grpc_server import WorkerToolRuntimeService
from worker.runtime.computer_use_adapter import (
    COMPUTER_USE_SCHEMA_DIGEST,
    COMPUTER_USE_SOURCE_ID,
    COMPUTER_USE_TOOL_NAME,
    ComputerUseArgumentsError,
    ComputerUseToolAdapter,
    configured_computer_use_adapter,
    computer_action_digest,
)
from worker.runtime.computer_use_client import (
    ComputerUseActionExecutionReceipt,
    ComputerUseBrokerConfiguration,
    ComputerUseBrokerTransportError,
    ComputerUseCancellationReceipt,
    ComputerUseCloseReceipt,
    ComputerUseHandshakeReceipt,
    ComputerUsePermissionReceipt,
    ComputerUseSessionCancellationReceipt,
)
from worker.runtime.tool_execution_runtime import (
    ToolExecutionCall,
    ToolCallIdentityError,
    ToolExecutionContext,
    ToolExecutionRuntime,
)


_CAPABILITY = b"python-computer-broker-capability-v1"
_AUTHORIZATION_SIGNATURE = b"s" * 64


class _ManualMonotonicClock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _FakeComputerUseClient:
    def __init__(self) -> None:
        self.configuration = ComputerUseBrokerConfiguration(
            socket_path="/private/tmp/melix-fake-computer.sock",
            client_instance_id="fake-worker",
            caller_bundle_id="com.melix.worker",
            caller_team_id="MELIXTEAM",
            verification_capability=_CAPABILITY,
            request_timeout_seconds=1,
        )
        self.requests: list[str] = []
        self.request_deadlines: list[tuple[str, int]] = []
        self.open_started = asyncio.Event()
        self.open_release: asyncio.Event | None = None
        self.action_registered = asyncio.Event()
        self.action_cancelled = asyncio.Event()
        self.cancel_count = 0
        self.session_cancel_count = 0
        self.closed = False
        self.invalid_lease = False
        self.cross_session_capture = False
        self.rejected_capture_authorization_signatures: set[bytes] = set()
        self.cancel_dispositions: list[str] = []
        self.cancel_error = False
        self.session_cancel_error = False
        self.handshake_error = False
        self.close_refused = False

    async def handshake(self) -> ComputerUseHandshakeReceipt:
        self.requests.append("handshake")
        if self.handshake_error:
            raise ComputerUseBrokerTransportError("unavailable")
        return ComputerUseHandshakeReceipt(
            protocol_version="1",
            broker_version="fake-1",
            broker_instance_id="fake-broker",
            features=("screen_capture_window", "ax_semantic_press"),
            screen_recording="granted",
            accessibility="granted",
        )

    async def get_permissions(
        self,
        *,
        authorization,
        deadline_unix_ms=0,
    ):
        self.request_deadlines.append(("permissions", deadline_unix_ms))
        assert authorization.key_id == "test-control-plane-key"
        self.requests.append("permissions")
        return ComputerUsePermissionReceipt(
            screen_recording="granted",
            accessibility="granted",
            coordinate_fallback_enabled=False,
            secure_field_actions_allowed=False,
            observed_at_unix_ms=1_800_000_000_000,
        )

    async def list_targets(
        self,
        *,
        authorization,
        deadline_unix_ms=0,
    ):
        self.request_deadlines.append(("list_targets", deadline_unix_ms))
        assert authorization.key_id == "test-control-plane-key"
        self.requests.append("list_targets")
        return computer_pb2.ListComputerTargetsResponse(
            targets=[
                computer_pb2.TargetIdentity(
                    bundle_id="com.example.Target",
                    application_name="Example Target",
                    process_id=42,
                    process_launch_identity="launch-1",
                    window_id=7,
                    window_title="Document",
                )
            ],
            observed_at_unix_ms=1_800_000_000_000,
        )

    async def open_session(self, request, *, deadline_unix_ms=0):
        self.request_deadlines.append(("open", deadline_unix_ms))
        self.requests.append("open")
        self.last_open = request
        self.open_started.set()
        if self.open_release is not None:
            await self.open_release.wait()
        identity = computer_pb2.ComputerSessionIdentity()
        identity.CopyFrom(request.identity)
        identity.session_id = "session-adapter"
        if self.invalid_lease:
            identity.actor_id = "wrong-actor"
        return computer_pb2.ComputerSessionLease(
            identity=identity,
            session_capability=b"secret-session-capability",
            broker_instance_id="fake-broker",
            allowed_targets=request.allowed_targets,
            limits=request.limits,
            opened_at_unix_ms=1_800_000_000_000,
        )

    async def capture_frame(self, request, *, deadline_unix_ms=0):
        self.request_deadlines.append(("capture", deadline_unix_ms))
        self.requests.append("capture")
        if (
            bytes(request.authorization.signature)
            in self.rejected_capture_authorization_signatures
        ):
            raise ComputerUseBrokerTransportError(
                "capture authorization rejected"
            )
        identity = computer_pb2.ComputerSessionIdentity()
        identity.CopyFrom(request.identity)
        if self.cross_session_capture:
            identity.session_id = "wrong-session"
        return computer_pb2.CaptureFrameResponse(
            identity=identity,
            actual_target=request.target,
            observation_id="observation-adapter",
            frame_generation=1,
            frame=computer_pb2.ArtifactReference(
                artifact_id="frame-adapter",
                relative_path="session-adapter/frame.png",
                sha256="b" * 64,
                media_type="image/png",
                byte_length=256,
                width=800,
                height=600,
                redaction_receipt_json='{"private":"not copied"}',
            ),
            elements=[
                computer_pb2.ElementHandle(
                    handle_id="save-button",
                    frame_generation=1,
                    role="AXButton",
                    title="Save",
                    enabled=True,
                )
            ],
            evidence_receipt_json='{"absolute_path":"/private/secret"}',
        )

    async def execute_action(
        self,
        request,
        *,
        deadline_unix_ms=0,
        on_registered=None,
    ):
        self.request_deadlines.append(("action", deadline_unix_ms))
        self.requests.append("action")
        self.last_action = request
        if on_registered is not None:
            result = on_registered()
            if asyncio.iscoroutine(result):
                await result
        self.action_registered.set()
        if request.action_id.startswith("press-cancel"):
            await self.action_cancelled.wait()
            return ComputerUseActionExecutionReceipt(
                action_id=request.action_id,
                attempt=request.attempt,
                status="cancelled",
                terminal_phase="cancelled",
                events=(),
                result=None,
                error=None,
            )
        if request.action_id == "press-error":
            error = computer_pb2.ComputerActionError(
                code="secure_field_refused",
                message="private message",
                retriable=False,
            )
            return ComputerUseActionExecutionReceipt(
                action_id=request.action_id,
                attempt=request.attempt,
                status="failed",
                terminal_phase="failed",
                events=(),
                result=None,
                error=error,
            )
        result = computer_pb2.ComputerActionResult(
            action_id=request.action_id,
            attempt=request.attempt,
            status="completed",
            requested_target=request.target,
            actual_target=request.target,
            before_observation_id=request.expected_observation_id,
            after_observation_id="observation-after",
            artifacts=[
                computer_pb2.ArtifactReference(
                    artifact_id="evidence",
                    relative_path="session-adapter/evidence.json",
                    sha256="c" * 64,
                    media_type="application/json",
                    byte_length=64,
                )
            ],
            adapter_kind="fake-ax",
            action_mode="ax_semantic_press",
            evidence_receipt_json='{"absolute_path":"/private/hidden"}',
        )
        return ComputerUseActionExecutionReceipt(
            action_id=request.action_id,
            attempt=request.attempt,
            status="completed",
            terminal_phase="completed",
            events=(
                computer_pb2.ComputerActionEvent(
                    identity=request.identity,
                    action_id=request.action_id,
                    attempt=request.attempt,
                    seq=1,
                    phase=computer_pb2.COMPUTER_ACTION_COMPLETED,
                    emitted_at_unix_ms=1_800_000_000_001,
                    result=result,
                ),
            ),
            result=result,
            error=None,
        )

    async def cancel_action(self, request, *, deadline_unix_ms=0):
        del deadline_unix_ms
        self.requests.append("cancel")
        self.cancel_count += 1
        if self.cancel_error:
            raise ComputerUseBrokerTransportError("cancel unavailable")
        disposition = (
            self.cancel_dispositions.pop(0)
            if self.cancel_dispositions
            else "accepted"
        )
        if disposition != "not_found":
            self.action_cancelled.set()
        return ComputerUseCancellationReceipt(
            action_id=request.action_id,
            attempt=request.attempt,
            cancellation_id=request.cancellation_id,
            disposition=disposition,
            side_effect_committed=False,
        )

    async def close_session(self, request, *, deadline_unix_ms=0):
        del deadline_unix_ms
        self.requests.append("close")
        return ComputerUseCloseReceipt(
            session_id=request.identity.session_id,
            closed=not self.close_refused,
            invalidated_handle_count=1,
            closed_at_unix_ms=1_800_000_000_002,
        )

    async def cancel_session(self, request, *, deadline_unix_ms=0):
        del deadline_unix_ms
        self.requests.append("cancel_session")
        self.session_cancel_count += 1
        self.last_session_cancel = request
        if self.session_cancel_error:
            raise ComputerUseBrokerTransportError(
                "session cancel unavailable"
            )
        self.action_cancelled.set()
        return ComputerUseSessionCancellationReceipt(
            session_id=request.identity.session_id,
            cancellation_id=request.cancellation_id,
            disposition="accepted",
            cancelled_action_ids=(),
            too_late_action_ids=(),
            cancelled_at_unix_ms=1_800_000_000_002,
        )

    async def close(self) -> None:
        self.closed = True


def _context(
    *,
    admission_state: str = "approved",
    run_id: str = "run-adapter",
    actor_id: str = "operator-1",
    policy_revision: str = "policy-v1",
    approval_grant_digest: str | None = None,
    deadline_unix_ms: int = 0,
    issued_at_unix_ms: int | None = None,
    authorization_signature: bytes = _AUTHORIZATION_SIGNATURE,
) -> ToolExecutionContext:
    issued_at_unix_ms = (
        issued_at_unix_ms
        if issued_at_unix_ms is not None
        else int(time.time() * 1_000)
    )
    effective_run_deadline = (
        deadline_unix_ms
        if deadline_unix_ms > 0
        else issued_at_unix_ms + 300_000
    )
    expires_at_unix_ms = min(
        issued_at_unix_ms + 60_000,
        effective_run_deadline,
    )
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:32].strip("_")
    artifact_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    authorization_payload = json.dumps(
        {
            "schema_version": "melix.computer.tool-authorization.v2",
            "key_id": "test-control-plane-key",
            "run_id": run_id,
            "session_id": "chat-session",
            "branch_id": "branch-main",
            "actor_id": actor_id,
            "source_id": COMPUTER_USE_SOURCE_ID,
            "tool_name": COMPUTER_USE_TOOL_NAME,
            "artifact_root": (
                f"agent-{safe_prefix or 'run'}-{artifact_digest}"
            ),
            "maximum_frames": 16,
            "maximum_actions": 8,
            "maximum_artifact_bytes": 16 * 1_024 * 1_024,
            "idle_deadline_unix_ms": min(
                issued_at_unix_ms + 60_000,
                effective_run_deadline,
            ),
            "absolute_deadline_unix_ms": min(
                issued_at_unix_ms + 300_000,
                effective_run_deadline,
            ),
            "request_deadline_unix_ms": expires_at_unix_ms,
            "issued_at_unix_ms": issued_at_unix_ms,
            "expires_at_unix_ms": expires_at_unix_ms,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ToolExecutionContext(
        run_id=run_id,
        session_id="chat-session",
        branch_id="branch-main",
        actor_id=actor_id,
        admission_state=admission_state,
        approval_grant_digest=(
            approval_grant_digest
            if approval_grant_digest is not None
            else (
                "approval-grant-digest"
                if admission_state in {"approved", "allow"}
                else ""
            )
        ),
        policy_revision=policy_revision,
        deadline_unix_ms=deadline_unix_ms,
        control_plane_authorization_key_id="test-control-plane-key",
        control_plane_authorization_algorithm="ed25519",
        control_plane_authorization_payload=authorization_payload,
        control_plane_authorization_signature=authorization_signature,
    )


def _target_payload() -> dict[str, object]:
    return {
        "bundle_id": "com.example.Target",
        "process_id": 42,
        "process_launch_identity": "launch-1",
        "window_id": 7,
        "window_title": "Target Window",
    }


def _call(
    call_id: str,
    arguments: dict[str, object],
) -> ToolExecutionCall:
    return ToolExecutionCall(
        call_id=call_id,
        tool_name=COMPUTER_USE_TOOL_NAME,
        source_id=COMPUTER_USE_SOURCE_ID,
        arguments=arguments,
        expected_schema_digest=COMPUTER_USE_SCHEMA_DIGEST,
        idempotency_key=f"idempotency-{call_id}",
    )


async def _open_and_capture(runtime: ToolExecutionRuntime) -> None:
    opened = await runtime.execute(
        _call(
            "open-computer",
            {
                "operation": "open_session",
                "allowed_targets": [_target_payload()],
            },
        ),
        _context(),
    )
    assert opened.observation.payload["session_id"] == "session-adapter"
    captured = await runtime.execute(
        _call(
            "capture-computer",
            {
                "operation": "capture_frame",
                "session_id": "session-adapter",
                "target": _target_payload(),
            },
        ),
        _context(),
    )
    assert captured.observation.payload["observation_id"] == (
        "observation-adapter"
    )


def test_computer_adapter_registers_and_executes_bounded_workflow() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        runtime = ToolExecutionRuntime(
            computer_use_adapter=ComputerUseToolAdapter(client)
        )
        try:
            catalog = await runtime.list_tools()
            tool = next(
                item
                for item in catalog.tools
                if item.source_id == COMPUTER_USE_SOURCE_ID
            )
            assert tool.name == COMPUTER_USE_TOOL_NAME
            assert tool.risk_class == "computer_control"
            assert catalog.source_count >= 2
            assert catalog.live_source_count >= 1

            permissions = await runtime.execute(
                _call("permissions-computer", {"operation": "get_permissions"}),
                _context(admission_state="allow"),
            )
            assert permissions.status == "completed"
            assert permissions.observation.payload["accessibility"] == "granted"
            assert permissions.observation.payload["action_surface"] == (
                "ax_semantic_press_only"
            )
            assert permissions.observation.payload["maximum_frames"] == 16
            assert permissions.observation.payload["maximum_actions"] == 8
            assert permissions.observation.payload["maximum_artifact_bytes"] == (
                16 * 1_024 * 1_024
            )
            assert permissions.observation.payload["idle_timeout_seconds"] == 60
            assert permissions.observation.payload["absolute_timeout_seconds"] == 300
            assert permissions.receipt[
                "operator_projection_schema_version"
            ] == "melix.computer_use_operator_projection.v1"
            assert permissions.receipt["operator_projection"] == {
                "operation": "get_permissions",
                "screen_recording": "granted",
                "accessibility": "granted",
                "observed_at_unix_ms": 1_800_000_000_000,
                "maximum_frames": 16,
                "maximum_actions": 8,
                "maximum_artifact_bytes": 16 * 1_024 * 1_024,
                "idle_timeout_seconds": 60,
                "absolute_timeout_seconds": 300,
            }
            targets = await runtime.execute(
                _call("list-computer-targets", {"operation": "list_targets"}),
                _context(admission_state="allow"),
            )
            assert targets.status == "completed"
            assert targets.observation.payload["observed_at_unix_ms"] == (
                1_800_000_000_000
            )
            assert targets.observation.payload["targets"] == [
                {
                    "bundle_id": "com.example.Target",
                    "application_name": "Example Target",
                    "process_id": 42,
                    "process_launch_identity": "launch-1",
                    "window_id": 7,
                    "window_title": "Document",
                }
            ]
            assert targets.receipt["operator_projection"]["targets"] == (
                targets.observation.payload["targets"]
            )
            await _open_and_capture(runtime)
            assert client.last_open.limits.maximum_artifact_bytes == (
                16 * 1_024 * 1_024
            )
            assert client.last_open.limits.idle_deadline_unix_ms > 0
            assert (
                client.last_open.limits.absolute_deadline_unix_ms
                >= client.last_open.limits.idle_deadline_unix_ms
            )

            pressed = await runtime.execute(
                _call(
                    "press-computer",
                    {
                        "operation": "press_element",
                        "session_id": "session-adapter",
                        "target": _target_payload(),
                        "expected_observation_id": "observation-adapter",
                        "expected_frame_generation": 1,
                        "element": {
                            "handle_id": "save-button",
                            "title": "Save",
                            "role": "AXButton",
                        },
                    },
                ),
                _context(admission_state="allow"),
            )
            assert pressed.status == "completed"
            assert pressed.adapter_kind == "computer"
            assert pressed.receipt["approval_grant_present"] is True
            assert pressed.observation.payload["result"]["action_mode"] == (
                "ax_semantic_press"
            )
            assert pressed.receipt["operator_projection"] == {
                "operation": "press_element",
                "session_id": "session-adapter",
                "action_id": "press-computer",
                "attempt": 1,
                "status": "completed",
                "terminal_phase": "completed",
                "result": {
                    "status": "completed",
                    "actual_target": {
                        "bundle_id": "com.example.Target",
                        "application_name": "",
                        "process_id": 42,
                        "process_launch_identity": "launch-1",
                        "window_id": 7,
                        "window_title": "Target Window",
                    },
                },
            }
            encoded = json.dumps(
                {
                    "observation": pressed.observation.as_agentic_trace_observation(),
                    "receipt": pressed.receipt,
                },
                sort_keys=True,
            )
            assert "secret-session-capability" not in encoded
            assert "/private/hidden" not in encoded
            assert "/private/secret" not in encoded
            assert (
                client.last_action.authorization.key_id
                == "test-control-plane-key"
            )

            closed = await runtime.execute(
                _call(
                    "close-computer",
                    {
                        "operation": "close_session",
                        "session_id": "session-adapter",
                    },
                ),
                _context(admission_state="allow"),
            )
            assert closed.observation.payload["closed"] is True
        finally:
            await runtime.close()
        assert client.closed is True

    asyncio.run(exercise())


def test_long_run_deadline_uses_short_lived_broker_request_deadlines() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        run_deadline_unix_ms = int(time.time() * 1_000) + 15 * 60 * 1_000
        context = _context(deadline_unix_ms=run_deadline_unix_ms)
        payload = json.loads(
            context.control_plane_authorization_payload.decode("utf-8")
        )
        expected_request_deadline = payload["request_deadline_unix_ms"]
        try:
            opened = await adapter.execute(
                _call(
                    "open-long-run",
                    {
                        "operation": "open_session",
                        "allowed_targets": [_target_payload()],
                    },
                ),
                context,
            )
            assert opened.status == "completed"
            captured = await adapter.execute(
                _call(
                    "capture-long-run",
                    {
                        "operation": "capture_frame",
                        "session_id": "session-adapter",
                        "target": _target_payload(),
                    },
                ),
                context,
            )
            assert captured.status == "completed"
            assert client.request_deadlines[:2] == [
                ("open", expected_request_deadline),
                ("capture", expected_request_deadline),
            ]
            assert expected_request_deadline < run_deadline_unix_ms
            assert client.last_open.limits.idle_deadline_unix_ms == (
                payload["idle_deadline_unix_ms"]
            )
            assert client.last_open.limits.absolute_deadline_unix_ms == (
                payload["absolute_deadline_unix_ms"]
            )
        finally:
            await adapter.close()

    asyncio.run(exercise())


def test_computer_action_requires_exact_approval_and_latest_frame() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        runtime = ToolExecutionRuntime(
            computer_use_adapter=ComputerUseToolAdapter(client)
        )
        try:
            await _open_and_capture(runtime)
            call = _call(
                "press-without-approval",
                {
                    "operation": "press_element",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                    "expected_observation_id": "stale-observation",
                    "expected_frame_generation": 1,
                    "element": {"title": "Save", "role": "AXButton"},
                },
            )
            denied = await runtime.execute(
                call,
                _context(
                    admission_state="allow",
                    approval_grant_digest="",
                ),
            )
            assert denied.status == "failed"
            assert denied.receipt["error_code"] == (
                "computer_use_approval_invalid"
            )

            stale = await runtime.execute(
                _call("press-stale", dict(call.arguments)),
                _context(),
            )
            assert stale.status == "failed"
            assert stale.receipt["error_code"] == "computer_use_session_invalid"
            assert "action" not in client.requests
        finally:
            await runtime.close()

    asyncio.run(exercise())


def test_computer_action_cancellation_propagates_to_broker() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        runtime = ToolExecutionRuntime(
            computer_use_adapter=ComputerUseToolAdapter(client)
        )
        try:
            await _open_and_capture(runtime)
            call = _call(
                "press-cancel",
                {
                    "operation": "press_element",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                    "expected_observation_id": "observation-adapter",
                    "expected_frame_generation": 1,
                    "element": {
                        "handle_id": "save-button",
                        "title": "Save",
                        "role": "AXButton",
                    },
                },
            )
            task = asyncio.create_task(runtime.execute(call, _context()))
            await asyncio.wait_for(client.action_registered.wait(), timeout=1)
            cancellation_started = time.perf_counter()
            cancellation = await runtime.cancel(
                "run-adapter",
                "press-cancel",
                _context().owner,
            )
            cancellation_elapsed_ms = (
                time.perf_counter() - cancellation_started
            ) * 1_000
            assert cancellation.disposition == "accepted"
            assert cancellation.adapter_kind == "computer"
            assert cancellation_elapsed_ms < 250
            result = await task
            assert result.status == "cancelled"
            assert client.cancel_count == 1
            assert client.session_cancel_count == 1
            repeated = await runtime.cancel(
                "run-adapter",
                "press-cancel",
                _context().owner,
            )
            assert repeated.disposition == "already_terminal"
        finally:
            await runtime.close()

    asyncio.run(exercise())


def test_adapter_cancellation_tombstones_are_bounded_and_expire_safely() -> None:
    async def exercise() -> None:
        clock = _ManualMonotonicClock()
        adapter = ComputerUseToolAdapter(
            _FakeComputerUseClient(),
            maximum_tombstone_records=2,
            tombstone_retention_seconds=10,
            monotonic_clock=clock,
        )
        try:
            first = await adapter.cancel("bounded-run-1", "bounded-call-1")
            second = await adapter.cancel("bounded-run-2", "bounded-call-2")
            assert first.disposition == "not_found"
            assert second.disposition == "not_found"
            assert (
                await adapter.cancel("bounded-run-1", "bounded-call-1")
            ) is first
            assert len(adapter._cancelled_runs) == 2
            assert len(adapter._cancellation_receipts) == 2

            at_capacity = await adapter.cancel(
                "bounded-run-3",
                "bounded-call-3",
            )
            assert at_capacity.disposition == "too_late"
            assert at_capacity.error_code == (
                "computer_use_tombstone_capacity_exhausted"
            )
            assert len(adapter._cancelled_runs) == 2
            assert len(adapter._cancellation_receipts) == 2

            cleanup = await adapter.cancel(
                "bounded-run-1",
                "__run_cleanup__:stable-id",
            )
            assert cleanup.disposition == "not_found"
            assert cleanup.error_code == ""

            clock.advance(11)
            after_horizon = await adapter.cancel(
                "bounded-run-3",
                "bounded-call-3",
            )
            assert after_horizon.disposition == "not_found"
            assert set(adapter._cancelled_runs) == {"bounded-run-3"}
            assert set(adapter._cancellation_receipts) == {
                ("bounded-run-3", "bounded-call-3")
            }
        finally:
            await adapter.close()

    asyncio.run(exercise())


def test_adapter_run_tombstone_horizon_starts_after_session_cleanup() -> None:
    async def exercise() -> None:
        clock = _ManualMonotonicClock()

        class _DelayedSessionCancellationClient(_FakeComputerUseClient):
            async def cancel_session(self, request, *, deadline_unix_ms=0):
                clock.advance(8)
                return await super().cancel_session(
                    request,
                    deadline_unix_ms=deadline_unix_ms,
                )

        adapter = ComputerUseToolAdapter(
            _DelayedSessionCancellationClient(),
            maximum_tombstone_records=1,
            tombstone_retention_seconds=10,
            monotonic_clock=clock,
        )
        try:
            opened = await adapter.execute(
                _call(
                    "open-delayed-cleanup",
                    {
                        "operation": "open_session",
                        "allowed_targets": [_target_payload()],
                    },
                ),
                _context(run_id="delayed-cleanup-run"),
            )
            assert opened.status == "completed"

            terminal = await adapter.cancel(
                "delayed-cleanup-run",
                "__run_cleanup__:stop-delayed-cleanup",
            )
            assert terminal.disposition == "accepted"
            assert clock() == 1_008
            assert adapter._cancelled_runs["delayed-cleanup-run"] == 1_018

            clock.advance(3)
            blocked = await adapter.cancel(
                "blocked-before-terminal-horizon",
                "blocked-call",
            )
            assert blocked.disposition == "too_late"
            assert blocked.error_code == (
                "computer_use_tombstone_capacity_exhausted"
            )

            clock.advance(8)
            after_horizon = await adapter.cancel(
                "admitted-after-terminal-horizon",
                "admitted-call",
            )
            assert after_horizon.disposition == "not_found"
            assert set(adapter._cancelled_runs) == {
                "admitted-after-terminal-horizon"
            }
        finally:
            await adapter.close()

    asyncio.run(exercise())


def test_terminal_action_receipt_preserves_the_commit_boundary() -> None:
    adapter = ComputerUseToolAdapter(_FakeComputerUseClient())
    precommit_failure = ComputerUseActionExecutionReceipt(
        action_id="precommit-failure",
        attempt=1,
        status="failed",
        terminal_phase="failed",
        events=(
            computer_pb2.ComputerActionEvent(
                action_id="precommit-failure",
                attempt=1,
                seq=1,
                phase=computer_pb2.COMPUTER_ACTION_PRECONDITION_CHECKED,
                emitted_at_unix_ms=1_800_000_000_001,
            ),
        ),
        result=None,
        error=computer_pb2.ComputerActionError(
            code="precondition_failed",
            retriable=False,
        ),
    )
    postcommit_failure = ComputerUseActionExecutionReceipt(
        action_id="postcommit-failure",
        attempt=1,
        status="failed",
        terminal_phase="failed",
        events=(
            computer_pb2.ComputerActionEvent(
                action_id="postcommit-failure",
                attempt=1,
                seq=1,
                phase=computer_pb2.COMPUTER_ACTION_COMMIT_STARTED,
                emitted_at_unix_ms=1_800_000_000_001,
            ),
            computer_pb2.ComputerActionEvent(
                action_id="postcommit-failure",
                attempt=1,
                seq=2,
                phase=computer_pb2.COMPUTER_ACTION_FAILED,
                emitted_at_unix_ms=1_800_000_000_002,
            ),
        ),
        result=None,
        error=computer_pb2.ComputerActionError(
            code="press_transport_failed",
            retriable=False,
        ),
    )

    assert adapter._execution_may_have_side_effect(precommit_failure) is False
    assert adapter._execution_may_have_side_effect(postcommit_failure) is True


def test_run_cancellation_closes_sessions_without_an_active_action() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        now_unix_ms = int(time.time() * 1_000)
        open_context = _context(issued_at_unix_ms=now_unix_ms)
        opened = await adapter.execute(
            _call(
                "open-idle-session",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            open_context,
        )
        assert opened.status == "completed"

        latest_context = _context(
            deadline_unix_ms=now_unix_ms + 240_000,
            issued_at_unix_ms=now_unix_ms + 1_000,
        )
        assert (
            latest_context.control_plane_authorization_payload
            != open_context.control_plane_authorization_payload
        )
        captured = await adapter.execute(
            _call(
                "capture-before-run-stop",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            latest_context,
        )
        assert captured.status == "completed"

        receipt = await adapter.cancel("run-adapter", "run-stop")
        assert receipt.disposition == "accepted"
        assert receipt.side_effect_committed is False
        assert client.cancel_count == 0
        assert client.session_cancel_count == 1
        assert (
            client.last_session_cancel.authorization.signed_payload
            == latest_context.control_plane_authorization_payload
        )
        repeated = await adapter.cancel("run-adapter", "run-stop")
        assert repeated == receipt
        assert client.session_cancel_count == 1

        capture = await adapter.execute(
            _call(
                "capture-after-run-stop",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            _context(),
        )
        assert capture.status == "failed"
        assert capture.receipt["error_code"] == "computer_use_session_invalid"
        await adapter.close()
        assert client.session_cancel_count == 1

    asyncio.run(exercise())


def test_run_cancellation_retains_newest_session_authorization() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        now_unix_ms = int(time.time() * 1_000)
        opened = await adapter.execute(
            _call(
                "open-session-before-out-of-order-calls",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            _context(issued_at_unix_ms=now_unix_ms),
        )
        assert opened.status == "completed"

        newest_context = _context(
            issued_at_unix_ms=now_unix_ms + 20_000,
            deadline_unix_ms=now_unix_ms + 280_000,
        )
        captured = await adapter.execute(
            _call(
                "newest-session-call",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            newest_context,
        )
        assert captured.status == "completed"

        delayed_older_context = _context(
            issued_at_unix_ms=now_unix_ms + 10_000,
            deadline_unix_ms=now_unix_ms + 280_000,
        )
        delayed = await adapter.execute(
            _call(
                "delayed-older-session-call",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            delayed_older_context,
        )
        assert delayed.status == "completed"

        equal_freshness_context = _context(
            issued_at_unix_ms=now_unix_ms + 20_000,
            deadline_unix_ms=now_unix_ms + 280_000,
            authorization_signature=b"e" * 64,
        )
        equal_freshness = await adapter.execute(
            _call(
                "equal-freshness-session-call",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            equal_freshness_context,
        )
        assert equal_freshness.status == "completed"

        receipt = await adapter.cancel("run-adapter", "run-stop")
        assert receipt.disposition == "accepted"
        assert (
            client.last_session_cancel.authorization.signed_payload
            == newest_context.control_plane_authorization_payload
        )
        assert (
            client.last_session_cancel.authorization.signature
            == newest_context.control_plane_authorization_signature
        )
        await adapter.close()

    asyncio.run(exercise())


def test_rejected_newer_authorization_does_not_poison_session_cleanup() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        now_unix_ms = int(time.time() * 1_000)
        opened = await adapter.execute(
            _call(
                "open-session-before-rejected-refresh",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            _context(issued_at_unix_ms=now_unix_ms),
        )
        assert opened.status == "completed"

        accepted_context = _context(
            issued_at_unix_ms=now_unix_ms + 10_000,
            deadline_unix_ms=now_unix_ms + 280_000,
            authorization_signature=b"a" * 64,
        )
        accepted = await adapter.execute(
            _call(
                "accepted-authorization-refresh",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            accepted_context,
        )
        assert accepted.status == "completed"

        rejected_context = _context(
            issued_at_unix_ms=now_unix_ms + 20_000,
            deadline_unix_ms=now_unix_ms + 280_000,
            authorization_signature=b"r" * 64,
        )
        client.rejected_capture_authorization_signatures.add(b"r" * 64)
        rejected = await adapter.execute(
            _call(
                "rejected-authorization-refresh",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            rejected_context,
        )
        assert rejected.status == "failed"
        assert rejected.receipt["error_code"] == (
            "computer_broker_transport_error"
        )

        receipt = await adapter.cancel("run-adapter", "run-stop")
        assert receipt.disposition == "accepted"
        assert (
            client.last_session_cancel.authorization.signed_payload
            == accepted_context.control_plane_authorization_payload
        )
        assert (
            client.last_session_cancel.authorization.signature
            == accepted_context.control_plane_authorization_signature
        )
        await adapter.close()

    asyncio.run(exercise())


def test_runtime_run_cleanup_revokes_a_completed_open_session() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        runtime = ToolExecutionRuntime(
            computer_use_adapter=ComputerUseToolAdapter(client)
        )
        context = _context(run_id="run-completed-open")
        try:
            opened = await runtime.execute(
                _call(
                    "open-completed-session",
                    {
                        "operation": "open_session",
                        "allowed_targets": [_target_payload()],
                    },
                ),
                context,
            )
            assert opened.status == "completed"
            assert client.session_cancel_count == 0

            cleanup = await runtime.cancel_run(
                context.run_id,
                context.owner,
                "control-plane-stop",
            )
            assert cleanup.disposition == "accepted"
            assert cleanup.computer_use_disposition == "accepted"
            assert cleanup.side_effect_state == "none"
            assert client.session_cancel_count == 1
            assert client.last_session_cancel.identity.agent_run_id == (
                context.run_id
            )
        finally:
            await runtime.close()

    asyncio.run(exercise())


def test_run_cancellation_reports_session_revocation_failure() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        opened = await adapter.execute(
            _call(
                "open-cancel-error",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            _context(run_id="run-cancel-error"),
        )
        assert opened.status == "completed"

        client.session_cancel_error = True
        receipt = await adapter.cancel("run-cancel-error", "run-stop-error")
        assert receipt.disposition == "too_late"
        assert receipt.error_code == "computer_broker_transport_error"
        assert client.session_cancel_count == 1

        client.session_cancel_error = False
        await adapter.close()
        assert client.session_cancel_count == 2

    asyncio.run(exercise())


def test_run_cancellation_reconciles_a_session_opening_in_flight() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        client.open_release = asyncio.Event()
        runtime = ToolExecutionRuntime(
            computer_use_adapter=ComputerUseToolAdapter(client)
        )
        task = asyncio.create_task(
            runtime.execute(
                _call(
                    "open-cancelled-in-flight",
                    {
                        "operation": "open_session",
                        "allowed_targets": [_target_payload()],
                    },
                ),
                _context(),
            )
        )
        try:
            await asyncio.wait_for(client.open_started.wait(), timeout=1)
            cancellation = await runtime.cancel(
                "run-adapter",
                "open-cancelled-in-flight",
                _context().owner,
            )
            assert cancellation.disposition == "accepted"
            assert cancellation.side_effect_state == "none"
            result = await asyncio.wait_for(task, timeout=1)
            assert result.status == "cancelled"
            assert client.session_cancel_count == 0
        finally:
            client.open_release.set()
            await runtime.close()

        assert client.session_cancel_count == 1
        assert client.last_session_cancel.identity.session_id == "session-adapter"
        assert client.last_session_cancel.authorization.key_id == (
            "test-control-plane-key"
        )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "arguments",
    [
        {"maximum_frames": 0},
        {"maximum_actions": 33},
        {"maximum_artifact_bytes": 0},
        {"maximum_artifact_bytes": 64 * 1_024 * 1_024 + 1},
        {"idle_timeout_seconds": 0},
        {"idle_timeout_seconds": 301},
        {"session_ttl_seconds": 0},
        {"approval_ttl_seconds": 61},
    ],
)
def test_adapter_rejects_unsafe_runtime_limits(
    arguments: dict[str, int],
) -> None:
    with pytest.raises(ComputerUseArgumentsError):
        ComputerUseToolAdapter(_FakeComputerUseClient(), **arguments)


def test_adapter_validation_and_broker_failures_are_typed() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)

        mismatched_schema = ToolExecutionCall(
            call_id="schema-mismatch",
            tool_name=COMPUTER_USE_TOOL_NAME,
            source_id=COMPUTER_USE_SOURCE_ID,
            arguments={"operation": "get_permissions"},
            expected_schema_digest="wrong",
            idempotency_key="schema-mismatch",
        )
        assert (await adapter.execute(mismatched_schema, _context())).receipt[
            "error_code"
        ] == "computer_use_schema_changed"
        assert (
            await adapter.execute(
                _call("unknown-operation", {"operation": "unknown"}),
                _context(),
            )
        ).receipt["error_code"] == "computer_use_arguments_invalid"

        client.handshake_error = True
        assert (
            await adapter.execute(
                _call("permissions-error", {"operation": "get_permissions"}),
                _context(admission_state="allow"),
            )
        ).receipt["error_code"] == "computer_broker_transport_error"
        client.handshake_error = False

        open_arguments = {
            "operation": "open_session",
            "allowed_targets": [_target_payload()],
        }
        with pytest.raises(ToolCallIdentityError, match="branch_id"):
            ToolExecutionContext(
                run_id="run-adapter",
                session_id="chat-session",
                branch_id="",
                actor_id="operator-1",
                admission_state="approved",
                approval_grant_digest="approval",
                policy_revision="policy-v1",
            )
        no_idempotency = ToolExecutionCall(
            call_id="open-no-idempotency",
            tool_name=COMPUTER_USE_TOOL_NAME,
            source_id=COMPUTER_USE_SOURCE_ID,
            arguments=open_arguments,
            expected_schema_digest=COMPUTER_USE_SCHEMA_DIGEST,
        )
        assert (await adapter.execute(no_idempotency, _context())).status == (
            "failed"
        )
        for call_id, allowed_targets in (
            ("open-empty", []),
            ("open-duplicate", [_target_payload(), _target_payload()]),
        ):
            assert (
                await adapter.execute(
                    _call(
                        call_id,
                        {
                            "operation": "open_session",
                            "allowed_targets": allowed_targets,
                        },
                    ),
                    _context(),
                )
            ).status == "failed"
        assert (
            await adapter.execute(
                _call("open-expired", open_arguments),
                _context(deadline_unix_ms=1),
            )
        ).status == "failed"

        client.invalid_lease = True
        assert (
            await adapter.execute(
                _call("open-invalid-lease", open_arguments),
                _context(),
            )
        ).receipt["error_code"] == "computer_use_session_invalid"
        client.invalid_lease = False

        assert (
            await adapter.execute(
                _call(
                    "capture-missing-session",
                    {
                        "operation": "capture_frame",
                        "session_id": "missing",
                        "target": _target_payload(),
                    },
                ),
                _context(),
            )
        ).status == "failed"
        await adapter.execute(
            _call("open-validations", open_arguments),
            _context(deadline_unix_ms=int(time.time() * 1_000) + 60_000),
        )
        outside_target = _target_payload()
        outside_target["window_id"] = 99
        assert (
            await adapter.execute(
                _call(
                    "capture-outside",
                    {
                        "operation": "capture_frame",
                        "session_id": "session-adapter",
                        "target": outside_target,
                    },
                ),
                _context(),
            )
        ).status == "failed"
        assert (
            await adapter.execute(
                _call(
                    "capture-wrong-actor",
                    {
                        "operation": "capture_frame",
                        "session_id": "session-adapter",
                        "target": _target_payload(),
                    },
                ),
                _context(actor_id="different-operator"),
            )
        ).status == "failed"

        client.cross_session_capture = True
        assert (
            await adapter.execute(
                _call(
                    "capture-cross-session",
                    {
                        "operation": "capture_frame",
                        "session_id": "session-adapter",
                        "target": _target_payload(),
                    },
                ),
                _context(),
            )
        ).status == "failed"
        client.cross_session_capture = False
        captured = await adapter.execute(
            _call(
                "capture-validations",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                    "expected_previous_generation": 0,
                },
            ),
            _context(),
        )
        assert captured.status == "completed"

        base_press = {
            "operation": "press_element",
            "session_id": "session-adapter",
            "target": _target_payload(),
            "expected_observation_id": "observation-adapter",
            "expected_frame_generation": 1,
            "element": {"title": "Save", "role": "AXButton"},
        }
        assert (
            await adapter.execute(
                _call("press-no-policy", base_press),
                _context(policy_revision=""),
            )
        ).receipt["error_code"] == "computer_use_approval_invalid"
        no_action_idempotency = ToolExecutionCall(
            call_id="press-no-idempotency",
            tool_name=COMPUTER_USE_TOOL_NAME,
            source_id=COMPUTER_USE_SOURCE_ID,
            arguments=base_press,
            expected_schema_digest=COMPUTER_USE_SCHEMA_DIGEST,
        )
        assert (
            await adapter.execute(no_action_idempotency, _context())
        ).status == "failed"
        invalid_element = dict(base_press)
        invalid_element["element"] = {}
        assert (
            await adapter.execute(
                _call("press-invalid-element", invalid_element),
                _context(),
            )
        ).status == "failed"

        action_error = await adapter.execute(
            _call("press-error", base_press),
            _context(),
        )
        assert action_error.status == "failed"
        assert action_error.payload["error"]["code"] == (
            "secure_field_refused"
        )
        client.close_refused = True
        refused_close = await adapter.execute(
            _call(
                "close-refused",
                {
                    "operation": "close_session",
                    "session_id": "session-adapter",
                },
            ),
            _context(admission_state="allow"),
        )
        assert refused_close.status == "failed"
        client.close_refused = False
        closed = await adapter.execute(
            _call(
                "close-blank-reason",
                {
                    "operation": "close_session",
                    "session_id": "session-adapter",
                    "reason": "   ",
                },
            ),
            _context(admission_state="allow"),
        )
        assert closed.status == "completed"
        await adapter.close()

    asyncio.run(exercise())


def test_adapter_cancellation_retries_registration_and_fails_closed() -> None:
    async def exercise() -> None:
        client = _FakeComputerUseClient()
        adapter = ComputerUseToolAdapter(client)
        assert (await adapter.cancel("missing", "missing")).disposition == (
            "not_found"
        )
        await adapter.execute(
            _call(
                "open-cancel-direct",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            _context(),
        )
        await adapter.execute(
            _call(
                "capture-cancel-direct",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            _context(),
        )
        press = {
            "operation": "press_element",
            "session_id": "session-adapter",
            "target": _target_payload(),
            "expected_observation_id": "observation-adapter",
            "expected_frame_generation": 1,
            "element": {"title": "Save", "role": "AXButton"},
        }
        client.cancel_dispositions = ["not_found", "accepted"]
        task = asyncio.create_task(
            adapter.execute(_call("press-cancel-direct", press), _context())
        )
        await asyncio.wait_for(client.action_registered.wait(), timeout=1)
        receipt = await adapter.cancel("run-adapter", "press-cancel-direct")
        assert receipt.disposition == "accepted"
        assert (
            await adapter.cancel("run-adapter", "press-cancel-direct")
        ).disposition == "accepted"
        assert (await task).status == "cancelled"
        assert (
            await adapter.cancel("run-adapter", "press-cancel-direct")
        ).disposition == "accepted"

        retry_context = _context(run_id="run-adapter-retry")
        reopened = await adapter.execute(
            _call(
                "open-computer-retry",
                {
                    "operation": "open_session",
                    "allowed_targets": [_target_payload()],
                },
            ),
            retry_context,
        )
        assert reopened.status == "completed"
        recaptured = await adapter.execute(
            _call(
                "capture-computer-retry",
                {
                    "operation": "capture_frame",
                    "session_id": "session-adapter",
                    "target": _target_payload(),
                },
            ),
            retry_context,
        )
        assert recaptured.status == "completed"
        client.action_registered = asyncio.Event()
        client.action_cancelled = asyncio.Event()
        client.cancel_error = True
        task = asyncio.create_task(
            adapter.execute(_call("press-cancel-error", press), retry_context)
        )
        await asyncio.wait_for(client.action_registered.wait(), timeout=1)
        failed = await adapter.cancel(
            "run-adapter-retry",
            "press-cancel-error",
        )
        assert failed.disposition == "too_late"
        assert failed.error_code == "computer_broker_transport_error"
        client.cancel_error = False
        client.action_cancelled.set()
        assert (await task).status == "cancelled"
        await adapter.close()

    asyncio.run(exercise())


def test_helper_validation_and_disabled_factory_paths() -> None:
    assert configured_computer_use_adapter({}) is None
    adapter = ComputerUseToolAdapter(_FakeComputerUseClient())

    async def exercise() -> None:
        for call_id, arguments in (
            ("bad-target-type", {"operation": "open_session", "allowed_targets": [1]}),
            (
                "bad-target-string",
                {
                    "operation": "open_session",
                    "allowed_targets": [
                        {**_target_payload(), "bundle_id": ""}
                    ],
                },
            ),
            (
                "bad-target-integer",
                {
                    "operation": "open_session",
                    "allowed_targets": [
                        {**_target_payload(), "process_id": True}
                    ],
                },
            ),
            (
                "bad-target-range",
                {
                    "operation": "open_session",
                    "allowed_targets": [
                        {**_target_payload(), "window_id": 0}
                    ],
                },
            ),
        ):
            assert (
                await adapter.execute(_call(call_id, arguments), _context())
            ).status == "failed"
        await adapter.close()

    asyncio.run(exercise())


def test_action_digest_matches_swift_core_canonical_vector() -> None:
    digest = computer_action_digest(
        session_id="session-1",
        action_id="action-1",
        idempotency_key="idem-1",
        target=computer_pb2.TargetIdentity(
            bundle_id="com.example.App",
            process_id=42,
            process_launch_identity="launch-1",
            window_id=7,
            window_title="Target Window",
        ),
        expected_observation_id="frame-1",
        expected_frame_generation=3,
        element=computer_pb2.ElementHandle(
            handle_id="button.save",
            frame_generation=3,
            role="AXButton",
            title="Save",
            enabled=True,
        ),
    )
    assert digest == "6b8e5d8aec3bba7d5cdf0f8eed52a6563dc5968d4283cfe45620f67d8c8c264c"


def test_worker_service_registers_computer_only_with_explicit_configuration(
    tmp_path: Path,
) -> None:
    disabled = WorkerToolRuntimeService(environment={})
    try:
        catalog = disabled.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(),
            None,
        )
        assert all(tool.source_id != "computer" for tool in catalog.tools)
    finally:
        disabled.close()

    capability = tmp_path / "computer-capability.bin"
    capability.write_bytes(_CAPABILITY)
    capability.chmod(0o600)
    enabled = WorkerToolRuntimeService(
        environment={
            "MELIX_COMPUTER_BROKER_SOCKET": (
                "/private/tmp/melix-worker-computer.sock"
            ),
            "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID": "worker-service",
            "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "com.melix.worker",
            "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXTEAM",
            "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": str(
                capability
            ),
        }
    )
    try:
        assert enabled._runtime._computer_use_adapter is not None
        catalog = enabled.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(),
            None,
        )
        assert all(tool.source_id != "computer" for tool in catalog.tools)
        assert catalog.live_source_count == 0
    finally:
        enabled.close()
