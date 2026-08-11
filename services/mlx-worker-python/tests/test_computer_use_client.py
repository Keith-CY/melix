from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import grpc
import pytest

from packages.protocol.python.computer.v1 import computer_pb2, computer_pb2_grpc
from worker.runtime import computer_use_client as computer_use_client_module
from worker.runtime.computer_use_client import (
    ComputerUseBrokerClient,
    ComputerUseBrokerConfiguration,
    ComputerUseBrokerConfigurationError,
    ComputerUseBrokerProtocolError,
    ComputerUseBrokerRPCError,
    ComputerUseBrokerTransportError,
)


_CAPABILITY = b"python-computer-broker-capability-v1"


@pytest.mark.parametrize(
    ("mapper", "value"),
    [
        (computer_use_client_module._permission_state_name, 0),
        (computer_use_client_module._permission_state_name, 99),
        (computer_use_client_module._action_phase_name, 0),
        (computer_use_client_module._action_phase_name, 99),
        (computer_use_client_module._cancellation_disposition_name, 0),
        (computer_use_client_module._cancellation_disposition_name, 99),
        (
            computer_use_client_module._session_cancellation_disposition_name,
            0,
        ),
        (
            computer_use_client_module._session_cancellation_disposition_name,
            99,
        ),
    ],
)
def test_client_rejects_unspecified_and_unknown_broker_enums(
    mapper,
    value: int,
) -> None:
    with pytest.raises(ComputerUseBrokerProtocolError):
        mapper(value)


class _ComputerBrokerFixtureServicer(
    computer_pb2_grpc.ComputerUseBrokerServiceServicer
):
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.cancelled_actions: set[str] = set()
        self.cancelled_sessions: set[str] = set()
        self.cancellation_events: dict[str, asyncio.Event] = {}
        self.abort_methods: set[str] = set()
        self.invalid_responses: set[str] = set()
        self.handshake_protocol_version = "1"
        self.handshake_instance_id = "broker-python-test"

    async def _require_capability(self, request, context) -> None:
        if request.caller_verification_capability != _CAPABILITY:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "missing caller verification capability",
            )

    async def Handshake(self, request, context):
        self.requests.append("handshake")
        if "handshake" in self.abort_methods:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "unavailable")
        if (
            request.protocol_version != "1"
            or request.caller_bundle_id != "com.melix.worker"
            or request.caller_team_id != "MELIXTEAM"
            or request.caller_verification_capability != _CAPABILITY
        ):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "rejected")
        return computer_pb2.BrokerHandshakeResponse(
            protocol_version=self.handshake_protocol_version,
            broker_version="fixture-1",
            broker_instance_id=self.handshake_instance_id,
            features=["screen_capture_window", "ax_semantic_press"],
            permissions=_permissions(),
        )

    async def GetPermissions(self, request, context):
        self.requests.append("permissions")
        await self._require_capability(request, context)
        if request.authorization != _authorization():
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "missing control-plane authorization",
            )
        if "permissions_unavailable" in self.abort_methods:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "restarting")
        if "permissions" in self.abort_methods:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "denied")
        return _permissions()

    async def ListTargets(self, request, context):
        self.requests.append("list_targets")
        await self._require_capability(request, context)
        if request.authorization != _authorization():
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "missing control-plane authorization",
            )
        if "list_targets" in self.abort_methods:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "restarting")
        response = computer_pb2.ListComputerTargetsResponse(
            targets=[_target()],
            observed_at_unix_ms=1_800_000_000_000,
        )
        if "list_targets_timestamp" in self.invalid_responses:
            response.observed_at_unix_ms = 0
        if "list_targets_identity" in self.invalid_responses:
            response.targets[0].window_id = 0
        if "list_targets_duplicate" in self.invalid_responses:
            response.targets.append(_target())
        if "list_targets_oversized" in self.invalid_responses:
            del response.targets[:]
            for window_id in range(1, 130):
                target = _target()
                target.window_id = window_id
                response.targets.append(target)
        return response

    async def OpenSession(self, request, context):
        self.requests.append("open")
        await self._require_capability(request, context)
        if "open" in self.abort_methods:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid")
        identity = computer_pb2.ComputerSessionIdentity()
        identity.CopyFrom(request.identity)
        identity.session_id = "session-fixture"
        if "open_identity" in self.invalid_responses:
            identity.actor_id = "wrong-operator"
        allowed_targets = list(request.allowed_targets)
        if "open_scope" in self.invalid_responses:
            allowed_targets.append(
                computer_pb2.TargetIdentity(
                    bundle_id="com.example.Unapproved",
                    process_id=99,
                    process_launch_identity="launch-unapproved",
                    window_id=99,
                )
            )
        return computer_pb2.ComputerSessionLease(
            identity=identity,
            session_capability=b"session-capability",
            broker_instance_id="broker-python-test",
            allowed_targets=allowed_targets,
            limits=request.limits,
            opened_at_unix_ms=1_800_000_000_000,
        )

    async def CaptureFrame(self, request, context):
        self.requests.append("capture")
        await self._require_capability(request, context)
        if "capture" in self.abort_methods:
            await context.abort(grpc.StatusCode.NOT_FOUND, "missing")
        response = computer_pb2.CaptureFrameResponse(
            identity=request.identity,
            actual_target=request.target,
            observation_id="observation-1",
            frame_generation=1,
            frame=computer_pb2.ArtifactReference(
                artifact_id="frame-1",
                relative_path="session-fixture/frame-1.png",
                sha256="a" * 64,
                media_type="image/png",
                byte_length=128,
                width=640,
                height=480,
                redaction_receipt_json='{"applied":false}',
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
            evidence_receipt_json='{"capture":"ok"}',
        )
        if "capture" in self.invalid_responses:
            response.observation_id = ""
        return response

    async def ExecuteAction(self, request, context):
        self.requests.append("action")
        await self._require_capability(request, context)
        if request.action_id == "action-rpc-error":
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "failed")
        cancellation = self.cancellation_events.setdefault(
            request.action_id,
            asyncio.Event(),
        )
        first_action_id = (
            "wrong-action"
            if request.action_id == "action-bad-correlation"
            else request.action_id
        )
        first_sequence = 2 if request.action_id == "action-bad-sequence" else 1
        yield computer_pb2.ComputerActionEvent(
            identity=request.identity,
            action_id=first_action_id,
            attempt=request.attempt,
            seq=first_sequence,
            phase=computer_pb2.COMPUTER_ACTION_QUEUED,
            emitted_at_unix_ms=1_800_000_000_001,
        )
        if request.action_id == "action-no-terminal":
            return
        if request.action_id == "action-slow":
            await cancellation.wait()
            return
        if request.action_id == "action-cancel":
            await cancellation.wait()
            yield computer_pb2.ComputerActionEvent(
                identity=request.identity,
                action_id=request.action_id,
                attempt=request.attempt,
                seq=2,
                phase=computer_pb2.COMPUTER_ACTION_CANCELLED,
                emitted_at_unix_ms=1_800_000_000_002,
                error=computer_pb2.ComputerActionError(
                    code="cancelled_before_commit",
                    message="cancelled",
                ),
            )
            return
        if request.action_id == "action-terminal-empty":
            yield computer_pb2.ComputerActionEvent(
                identity=request.identity,
                action_id=request.action_id,
                attempt=request.attempt,
                seq=2,
                phase=computer_pb2.COMPUTER_ACTION_FAILED,
                emitted_at_unix_ms=1_800_000_000_002,
            )
            return
        if request.action_id == "action-empty-result-status":
            yield computer_pb2.ComputerActionEvent(
                identity=request.identity,
                action_id=request.action_id,
                attempt=request.attempt,
                seq=2,
                phase=computer_pb2.COMPUTER_ACTION_COMPLETED,
                emitted_at_unix_ms=1_800_000_000_002,
                result=computer_pb2.ComputerActionResult(
                    action_id=request.action_id,
                    attempt=request.attempt,
                ),
            )
            return
        if request.action_id == "action-after-terminal":
            yield computer_pb2.ComputerActionEvent(
                identity=request.identity,
                action_id=request.action_id,
                attempt=request.attempt,
                seq=2,
                phase=computer_pb2.COMPUTER_ACTION_COMPLETED,
                emitted_at_unix_ms=1_800_000_000_002,
                result=computer_pb2.ComputerActionResult(
                    action_id=request.action_id,
                    attempt=request.attempt,
                    status="completed",
                ),
            )
            yield computer_pb2.ComputerActionEvent(
                identity=request.identity,
                action_id=request.action_id,
                attempt=request.attempt,
                seq=3,
                phase=computer_pb2.COMPUTER_ACTION_HEARTBEAT,
                emitted_at_unix_ms=1_800_000_000_003,
            )
            return
        yield computer_pb2.ComputerActionEvent(
            identity=request.identity,
            action_id=request.action_id,
            attempt=request.attempt,
            seq=2,
            phase=computer_pb2.COMPUTER_ACTION_COMPLETED,
            emitted_at_unix_ms=1_800_000_000_002,
            result=computer_pb2.ComputerActionResult(
                action_id=request.action_id,
                attempt=request.attempt,
                status="completed",
                requested_target=request.target,
                actual_target=request.target,
                before_observation_id=request.expected_observation_id,
                after_observation_id="observation-2",
                adapter_kind="fixture",
                action_mode="ax_semantic_press",
                evidence_receipt_json='{"action":"ok"}',
            ),
        )

    async def CancelAction(self, request, context):
        self.requests.append("cancel")
        await self._require_capability(request, context)
        if "cancel" in self.abort_methods:
            await context.abort(grpc.StatusCode.ABORTED, "aborted")
        self.cancelled_actions.add(request.action_id)
        self.cancellation_events.setdefault(
            request.action_id,
            asyncio.Event(),
        ).set()
        response = computer_pb2.CancelComputerActionResponse(
            action_id=request.action_id,
            attempt=request.attempt,
            cancellation_id=request.cancellation_id,
            disposition=computer_pb2.COMPUTER_CANCELLATION_ACCEPTED,
            side_effect_committed=False,
        )
        if "cancel" in self.invalid_responses:
            response.cancellation_id = "wrong-cancellation"
        return response

    async def CloseSession(self, request, context):
        self.requests.append("close")
        await self._require_capability(request, context)
        if "close" in self.abort_methods:
            await context.abort(grpc.StatusCode.NOT_FOUND, "missing")
        response = computer_pb2.CloseComputerSessionResponse(
            session_id=request.identity.session_id,
            closed=True,
            invalidated_handle_count=1,
            closed_at_unix_ms=1_800_000_000_003,
        )
        if "close" in self.invalid_responses:
            response.session_id = "wrong-session"
        return response

    async def CancelSession(self, request, context):
        self.requests.append("cancel_session")
        await self._require_capability(request, context)
        if "cancel_session" in self.abort_methods:
            await context.abort(grpc.StatusCode.ABORTED, "aborted")
        self.cancelled_sessions.add(request.identity.session_id)
        response = computer_pb2.CancelComputerSessionResponse(
            session_id=request.identity.session_id,
            cancellation_id=request.cancellation_id,
            disposition=(
                computer_pb2.COMPUTER_SESSION_CANCELLATION_ACCEPTED
            ),
            cancelled_action_ids=[],
            too_late_action_ids=[],
            cancelled_at_unix_ms=1_800_000_000_003,
        )
        if "cancel_session" in self.invalid_responses:
            response.cancellation_id = "wrong-session-cancellation"
        return response


@dataclass
class _LiveBrokerFixture:
    root: Path
    socket_path: str
    server: grpc.aio.Server
    servicer: _ComputerBrokerFixtureServicer

    async def stop(self) -> None:
        await self.server.stop(grace=None)
        shutil.rmtree(self.root, ignore_errors=True)


async def _start_broker() -> _LiveBrokerFixture:
    root = Path(tempfile.mkdtemp(prefix="mcu-py-", dir="/private/tmp"))
    root.chmod(0o700)
    socket_path = str(root / "broker.sock")
    server = grpc.aio.server()
    servicer = _ComputerBrokerFixtureServicer()
    computer_pb2_grpc.add_ComputerUseBrokerServiceServicer_to_server(
        servicer,
        server,
    )
    assert server.add_insecure_port(f"unix://{socket_path}")
    await server.start()
    os.chmod(socket_path, 0o600)
    return _LiveBrokerFixture(root, socket_path, server, servicer)


async def _restart_broker(
    fixture: _LiveBrokerFixture,
    *,
    broker_instance_id: str,
) -> None:
    await fixture.server.stop(grace=None)
    try:
        os.unlink(fixture.socket_path)
    except FileNotFoundError:
        pass
    server = grpc.aio.server()
    servicer = _ComputerBrokerFixtureServicer()
    servicer.handshake_instance_id = broker_instance_id
    computer_pb2_grpc.add_ComputerUseBrokerServiceServicer_to_server(
        servicer,
        server,
    )
    assert server.add_insecure_port(f"unix://{fixture.socket_path}")
    await server.start()
    os.chmod(fixture.socket_path, 0o600)
    fixture.server = server
    fixture.servicer = servicer


def _configuration(socket_path: str) -> ComputerUseBrokerConfiguration:
    return ComputerUseBrokerConfiguration(
        socket_path=socket_path,
        client_instance_id="python-worker-test",
        caller_bundle_id="com.melix.worker",
        caller_team_id="MELIXTEAM",
        verification_capability=_CAPABILITY,
        request_timeout_seconds=2,
    )


def _identity() -> computer_pb2.ComputerSessionIdentity:
    return computer_pb2.ComputerSessionIdentity(
        agent_run_id="run-1",
        request_id="request-1",
        tool_call_id="open-call",
        branch_id="branch-1",
        actor_id="operator-1",
    )


def _target() -> computer_pb2.TargetIdentity:
    return computer_pb2.TargetIdentity(
        bundle_id="com.example.Target",
        application_name="Example Target",
        process_id=42,
        process_launch_identity="launch-1",
        window_id=7,
        window_title="Document",
    )


def _authorization() -> computer_pb2.ControlPlaneToolAuthorization:
    return computer_pb2.ControlPlaneToolAuthorization(
        key_id="control-plane-test-key",
        algorithm="ed25519",
        signed_payload=b"signed-payload",
        signature=b"S" * 64,
    )


def _action(
    lease: computer_pb2.ComputerSessionLease,
    *,
    action_id: str,
) -> computer_pb2.ExecuteComputerActionRequest:
    return computer_pb2.ExecuteComputerActionRequest(
        identity=lease.identity,
        session_capability=lease.session_capability,
        target=_target(),
        action_id=action_id,
        attempt=1,
        idempotency_key=f"idempotency-{action_id}",
        expected_observation_id="observation-1",
        expected_frame_generation=1,
        approval=computer_pb2.ApprovalGrant(
            approval_id="approval-1",
            action_digest="fixture-digest",
            policy_hash="policy-v1",
            approved_at_unix_ms=1,
            expires_at_unix_ms=4_000_000_000_000,
            actor_id="operator-1",
            scope=f"run-1:{action_id}",
            verification_capability=_CAPABILITY,
        ),
        press_element=computer_pb2.PressElementAction(
            element=computer_pb2.ElementHandle(
                handle_id="save-button",
                frame_generation=1,
                role="AXButton",
                title="Save",
                enabled=True,
            )
        ),
    )


def _permissions() -> computer_pb2.PermissionSnapshot:
    return computer_pb2.PermissionSnapshot(
        screen_recording=computer_pb2.PERMISSION_GRANTED,
        accessibility=computer_pb2.PERMISSION_GRANTED,
        coordinate_fallback_enabled=False,
        secure_field_actions_allowed=False,
        observed_at_unix_ms=1_800_000_000_000,
    )


def test_real_private_uds_client_maps_full_broker_lifecycle() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            handshake = await client.handshake()
            assert handshake.broker_instance_id == "broker-python-test"
            assert handshake.screen_recording == "granted"
            permissions = await client.get_permissions(
                authorization=_authorization()
            )
            assert permissions.accessibility == "granted"
            assert permissions.secure_field_actions_allowed is False
            targets = await client.list_targets(authorization=_authorization())
            assert targets.observed_at_unix_ms == 1_800_000_000_000
            assert len(targets.targets) == 1
            assert targets.targets[0].application_name == "Example Target"

            open_request = computer_pb2.OpenComputerSessionRequest(
                identity=_identity(),
                allowed_targets=[_target()],
                artifact_root="run-1",
                limits=computer_pb2.ComputerSessionLimits(
                    maximum_frames=4,
                    maximum_actions=2,
                    maximum_artifact_bytes=16 * 1_024 * 1_024,
                    idle_deadline_unix_ms=3_999_999_760_000,
                    absolute_deadline_unix_ms=4_000_000_000_000,
                ),
                idempotency_key="open-idempotency",
            )
            lease = await client.open_session(open_request)
            assert lease.identity.session_id == "session-fixture"
            capture = await client.capture_frame(
                computer_pb2.CaptureFrameRequest(
                    identity=lease.identity,
                    session_capability=lease.session_capability,
                    target=_target(),
                    capture_id="capture-1",
                )
            )
            assert capture.observation_id == "observation-1"
            assert capture.elements[0].handle_id == "save-button"

            action = computer_pb2.ExecuteComputerActionRequest(
                identity=lease.identity,
                session_capability=lease.session_capability,
                target=_target(),
                action_id="action-complete",
                attempt=1,
                idempotency_key="action-idempotency",
                expected_observation_id=capture.observation_id,
                expected_frame_generation=capture.frame_generation,
                approval=computer_pb2.ApprovalGrant(
                    approval_id="approval-1",
                    action_digest="fixture-digest",
                    policy_hash="policy-v1",
                    approved_at_unix_ms=1,
                    expires_at_unix_ms=4_000_000_000_000,
                    actor_id="operator-1",
                    scope="run-1:action-complete",
                    verification_capability=_CAPABILITY,
                ),
                press_element=computer_pb2.PressElementAction(
                    element=capture.elements[0]
                ),
            )
            execution = await client.execute_action(action)
            assert execution.status == "completed"
            assert execution.terminal_phase == "completed"
            assert [event.seq for event in execution.events] == [1, 2]

            cancelled_action = computer_pb2.ExecuteComputerActionRequest()
            cancelled_action.CopyFrom(action)
            cancelled_action.action_id = "action-cancel"
            registered = asyncio.Event()
            action_task = asyncio.create_task(
                client.execute_action(
                    cancelled_action,
                    on_registered=registered.set,
                )
            )
            await asyncio.wait_for(registered.wait(), timeout=1)
            cancellation = await client.cancel_action(
                computer_pb2.CancelComputerActionRequest(
                    identity=lease.identity,
                    session_capability=lease.session_capability,
                    action_id="action-cancel",
                    attempt=1,
                    cancellation_id="cancel-1",
                )
            )
            assert cancellation.disposition == "accepted"
            assert cancellation.side_effect_committed is False
            cancelled = await action_task
            assert cancelled.status == "cancelled"

            session_cancellation = await client.cancel_session(
                computer_pb2.CancelComputerSessionRequest(
                    identity=lease.identity,
                    session_capability=lease.session_capability,
                    cancellation_id="cancel-session-1",
                    reason="operator stopped the run",
                    authorization=_authorization(),
                )
            )
            assert session_cancellation.disposition == "accepted"
            assert session_cancellation.session_id == "session-fixture"

            closed = await client.close_session(
                computer_pb2.CloseComputerSessionRequest(
                    identity=lease.identity,
                    session_capability=lease.session_capability,
                    reason="test_complete",
                )
            )
            assert closed.closed is True
            assert closed.invalidated_handle_count == 1
            assert fixture.servicer.requests == [
                "handshake",
                "permissions",
                "list_targets",
                "open",
                "capture",
                "action",
                "action",
                "cancel",
                "cancel_session",
                "close",
            ]
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_client_rejects_invalid_target_inventories() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            await client.handshake()
            for mode in (
                "list_targets_timestamp",
                "list_targets_identity",
                "list_targets_duplicate",
                "list_targets_oversized",
            ):
                fixture.servicer.invalid_responses.add(mode)
                with pytest.raises(ComputerUseBrokerProtocolError):
                    await client.list_targets(authorization=_authorization())
                fixture.servicer.invalid_responses.remove(mode)
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_client_reconnects_after_same_path_broker_replacement() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            original_identity = os.lstat(fixture.socket_path).st_ino
            first = await client.handshake()
            assert first.broker_instance_id == "broker-python-test"

            await _restart_broker(
                fixture,
                broker_instance_id="broker-python-restarted",
            )
            replacement_identity = os.lstat(fixture.socket_path).st_ino
            assert replacement_identity != original_identity

            second = await client.handshake()
            assert second.broker_instance_id == "broker-python-restarted"
            assert fixture.servicer.requests == ["handshake"]
            permissions = await client.get_permissions(
                authorization=_authorization()
            )
            assert permissions.screen_recording == "granted"
            assert fixture.servicer.requests == ["handshake", "permissions"]
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_unavailable_rpc_invalidates_connection_without_automatic_replay() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            await client.handshake()
            fixture.servicer.abort_methods.add("permissions_unavailable")
            with pytest.raises(ComputerUseBrokerRPCError) as failure:
                await client.get_permissions(authorization=_authorization())
            assert failure.value.status_code == grpc.StatusCode.UNAVAILABLE
            assert fixture.servicer.requests == ["handshake", "permissions"]

            fixture.servicer.abort_methods.remove("permissions_unavailable")
            permissions = await client.get_permissions(
                authorization=_authorization()
            )
            assert permissions.accessibility == "granted"
            assert fixture.servicer.requests == [
                "handshake",
                "permissions",
                "handshake",
                "permissions",
            ]
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_client_rejects_cross_scope_broker_responses() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        open_request = computer_pb2.OpenComputerSessionRequest(
            identity=_identity(),
            allowed_targets=[_target()],
            artifact_root="run-1",
            limits=computer_pb2.ComputerSessionLimits(
                maximum_frames=2,
                maximum_actions=2,
                absolute_deadline_unix_ms=4_000_000_000_000,
            ),
            idempotency_key="open-correlation",
        )
        try:
            for invalid_response in ("open_identity", "open_scope"):
                fixture.servicer.invalid_responses.add(invalid_response)
                with pytest.raises(ComputerUseBrokerProtocolError):
                    await client.open_session(open_request)
                fixture.servicer.invalid_responses.remove(invalid_response)

            lease = await client.open_session(open_request)
            fixture.servicer.invalid_responses.add("capture")
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.capture_frame(
                    computer_pb2.CaptureFrameRequest(
                        identity=lease.identity,
                        session_capability=lease.session_capability,
                        target=_target(),
                        capture_id="capture-invalid",
                    )
                )
            fixture.servicer.invalid_responses.remove("capture")

            fixture.servicer.invalid_responses.add("cancel")
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.cancel_action(
                    computer_pb2.CancelComputerActionRequest(
                        identity=lease.identity,
                        session_capability=lease.session_capability,
                        action_id="action-invalid-cancel",
                        attempt=1,
                        cancellation_id="cancel-correlation",
                    )
                )
            fixture.servicer.invalid_responses.remove("cancel")

            fixture.servicer.invalid_responses.add("cancel_session")
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.cancel_session(
                    computer_pb2.CancelComputerSessionRequest(
                        identity=lease.identity,
                        session_capability=lease.session_capability,
                        cancellation_id="cancel-session-correlation",
                        reason="test",
                    )
                )
            fixture.servicer.invalid_responses.remove("cancel_session")

            fixture.servicer.invalid_responses.add("close")
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.close_session(
                    computer_pb2.CloseComputerSessionRequest(
                        identity=lease.identity,
                        session_capability=lease.session_capability,
                        reason="test",
                    )
                )
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_configuration_is_explicit_and_capability_file_is_private(
    tmp_path: Path,
) -> None:
    assert ComputerUseBrokerConfiguration.from_environment({}) is None
    with pytest.raises(ComputerUseBrokerConfigurationError):
        ComputerUseBrokerConfiguration.from_environment(
            {"MELIX_COMPUTER_BROKER_SOCKET": "/private/tmp/missing.sock"}
        )

    capability = tmp_path / "capability.bin"
    capability.write_bytes(_CAPABILITY)
    capability.chmod(0o600)
    environment = {
        "MELIX_COMPUTER_BROKER_SOCKET": "/private/tmp/melix-private/broker.sock",
        "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID": "worker-1",
        "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "com.melix.worker",
        "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXTEAM",
        "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": str(capability),
        "MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS": "2500",
    }
    configured = ComputerUseBrokerConfiguration.from_environment(environment)
    assert configured is not None
    assert configured.verification_capability == _CAPABILITY
    assert configured.request_timeout_seconds == 2.5

    capability.chmod(0o644)
    with pytest.raises(ComputerUseBrokerConfigurationError):
        ComputerUseBrokerConfiguration.from_environment(environment)


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("client_instance_id", ""),
        ("verification_capability", b"short"),
        ("request_timeout_seconds", 0),
        ("socket_path", "relative.sock"),
        ("socket_path", "/private/tmp/../tmp/broker.sock"),
        ("socket_path", "/private/tmp/" + "x" * 100),
    ],
)
def test_configuration_rejects_invalid_security_boundaries(
    override: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "socket_path": "/private/tmp/melix-valid.sock",
        "client_instance_id": "worker",
        "caller_bundle_id": "com.melix.worker",
        "caller_team_id": "MELIXTEAM",
        "verification_capability": _CAPABILITY,
        "request_timeout_seconds": 1,
    }
    values[override] = value
    with pytest.raises(ComputerUseBrokerConfigurationError):
        ComputerUseBrokerConfiguration(**values)


def test_environment_rejects_invalid_timeout_and_capability_shape(
    tmp_path: Path,
) -> None:
    capability = tmp_path / "capability.bin"
    capability.write_bytes(_CAPABILITY)
    capability.chmod(0o600)
    environment = {
        "MELIX_COMPUTER_BROKER_SOCKET": "/private/tmp/melix-env.sock",
        "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID": "worker-1",
        "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "com.melix.worker",
        "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXTEAM",
        "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": str(capability),
    }
    for invalid_timeout in ("invalid", "0", "60001"):
        environment["MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS"] = invalid_timeout
        with pytest.raises(ComputerUseBrokerConfigurationError):
            ComputerUseBrokerConfiguration.from_environment(environment)

    environment.pop("MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS")
    capability.write_bytes(b"short")
    with pytest.raises(ComputerUseBrokerConfigurationError):
        ComputerUseBrokerConfiguration.from_environment(environment)
    capability.unlink()
    capability.mkdir()
    with pytest.raises(ComputerUseBrokerConfigurationError):
        ComputerUseBrokerConfiguration.from_environment(environment)


def test_client_maps_rpc_and_action_protocol_failures() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            first, second = await asyncio.gather(
                client.handshake(),
                client.handshake(),
            )
            assert first == second
            lease = await client.open_session(
                computer_pb2.OpenComputerSessionRequest(
                    identity=_identity(),
                    allowed_targets=[_target()],
                    artifact_root="run-1",
                    limits=computer_pb2.ComputerSessionLimits(
                        maximum_frames=2,
                        maximum_actions=2,
                        absolute_deadline_unix_ms=4_000_000_000_000,
                    ),
                    idempotency_key="open-errors",
                )
            )

            for method_name, operation in (
                (
                    "permissions",
                    lambda: client.get_permissions(
                        authorization=_authorization()
                    ),
                ),
                (
                    "open",
                    lambda: client.open_session(
                        computer_pb2.OpenComputerSessionRequest()
                    ),
                ),
                (
                    "capture",
                    lambda: client.capture_frame(
                        computer_pb2.CaptureFrameRequest()
                    ),
                ),
                (
                    "cancel",
                    lambda: client.cancel_action(
                        computer_pb2.CancelComputerActionRequest()
                    ),
                ),
                (
                    "cancel_session",
                    lambda: client.cancel_session(
                        computer_pb2.CancelComputerSessionRequest()
                    ),
                ),
                (
                    "close",
                    lambda: client.close_session(
                        computer_pb2.CloseComputerSessionRequest()
                    ),
                ),
            ):
                fixture.servicer.abort_methods.add(method_name)
                with pytest.raises(ComputerUseBrokerRPCError):
                    await operation()
                fixture.servicer.abort_methods.remove(method_name)

            with pytest.raises(ComputerUseBrokerRPCError):
                await client.execute_action(
                    _action(lease, action_id="action-rpc-error")
                )
            for action_id in (
                "action-bad-correlation",
                "action-bad-sequence",
                "action-no-terminal",
                "action-after-terminal",
            ):
                with pytest.raises(ComputerUseBrokerProtocolError):
                    await client.execute_action(
                        _action(lease, action_id=action_id)
                    )

            empty_terminal = await client.execute_action(
                _action(lease, action_id="action-terminal-empty")
            )
            assert empty_terminal.status == "failed"
            empty_status = await client.execute_action(
                _action(lease, action_id="action-empty-result-status")
            )
            assert empty_status.status == "completed"

            with pytest.raises(ComputerUseBrokerRPCError) as expired:
                await client.get_permissions(
                    authorization=_authorization(),
                    deadline_unix_ms=1,
                )
            assert expired.value.status_code == grpc.StatusCode.DEADLINE_EXCEEDED
            future = int(asyncio.get_running_loop().time() * 0) + 4_000_000_000_000
            assert (
                await client.get_permissions(
                    authorization=_authorization(),
                    deadline_unix_ms=future,
                )
            ).screen_recording == "granted"

            registered = asyncio.Event()

            async def registered_callback() -> None:
                registered.set()

            slow = asyncio.create_task(
                client.execute_action(
                    _action(lease, action_id="action-slow"),
                    on_registered=registered_callback,
                )
            )
            await asyncio.wait_for(registered.wait(), timeout=1)
            slow.cancel()
            with pytest.raises(asyncio.CancelledError):
                await slow
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_handshake_rejects_rpc_and_response_identity_failures() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        try:
            fixture.servicer.handshake_protocol_version = "2"
            client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.handshake()
            await client.close()

            fixture.servicer.handshake_protocol_version = "1"
            fixture.servicer.handshake_instance_id = ""
            client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
            with pytest.raises(ComputerUseBrokerProtocolError):
                await client.handshake()
            await client.close()

            fixture.servicer.handshake_instance_id = "broker-python-test"
            fixture.servicer.abort_methods.add("handshake")
            client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
            with pytest.raises(ComputerUseBrokerRPCError):
                await client.handshake()
            await client.close()
        finally:
            await fixture.stop()

    asyncio.run(exercise())


def test_client_rejects_non_private_socket_before_handshake() -> None:
    async def exercise() -> None:
        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            os.chmod(fixture.socket_path, 0o666)
            with pytest.raises(ComputerUseBrokerTransportError):
                await client.handshake()
            assert fixture.servicer.requests == []
        finally:
            await client.close()
            await fixture.stop()

    asyncio.run(exercise())


def test_client_rejects_non_socket_and_broad_parent_paths() -> None:
    async def exercise() -> None:
        root = Path(tempfile.mkdtemp(prefix="mcu-path-", dir="/private/tmp"))
        root.chmod(0o700)
        ordinary_file = root / "not-a-socket"
        ordinary_file.write_text("no", encoding="utf-8")
        client = ComputerUseBrokerClient(_configuration(str(ordinary_file)))
        try:
            with pytest.raises(ComputerUseBrokerTransportError):
                await client.handshake()
        finally:
            await client.close()
            shutil.rmtree(root, ignore_errors=True)

        fixture = await _start_broker()
        client = ComputerUseBrokerClient(_configuration(fixture.socket_path))
        try:
            fixture.root.chmod(0o755)
            with pytest.raises(ComputerUseBrokerTransportError):
                await client.handshake()
        finally:
            await client.close()
            fixture.root.chmod(0o700)
            await fixture.stop()

    asyncio.run(exercise())
