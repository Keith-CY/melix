from __future__ import annotations

import asyncio
import inspect
import os
import stat
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

import grpc

from packages.protocol.python.computer.v1 import computer_pb2, computer_pb2_grpc


_SOCKET_ENV = "MELIX_COMPUTER_BROKER_SOCKET"
_INSTANCE_ENV = "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID"
_BUNDLE_ENV = "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID"
_TEAM_ENV = "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID"
_CAPABILITY_FILE_ENV = "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE"
_PROTOCOL_ENV = "MELIX_COMPUTER_BROKER_PROTOCOL_VERSION"
_TIMEOUT_ENV = "MELIX_COMPUTER_BROKER_RPC_TIMEOUT_MS"


class ComputerUseBrokerClientError(RuntimeError):
    code = "computer_broker_client_error"


class ComputerUseBrokerConfigurationError(ComputerUseBrokerClientError):
    code = "computer_broker_configuration_invalid"


class ComputerUseBrokerTransportError(ComputerUseBrokerClientError):
    code = "computer_broker_transport_error"


class ComputerUseBrokerProtocolError(ComputerUseBrokerClientError):
    code = "computer_broker_protocol_error"


class ComputerUseBrokerRPCError(ComputerUseBrokerClientError):
    def __init__(self, status_code: grpc.StatusCode, message: str) -> None:
        self.status_code = status_code
        self.code = f"computer_broker_{status_code.name.lower()}"
        super().__init__(message)


@dataclass(frozen=True)
class ComputerUseBrokerConfiguration:
    socket_path: str
    client_instance_id: str
    caller_bundle_id: str
    caller_team_id: str
    verification_capability: bytes
    protocol_version: str = "1"
    request_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        _validate_standardized_absolute_path(
            self.socket_path,
            label="Computer Use broker socket",
            maximum_bytes=103,
        )
        for label, value in (
            ("client instance ID", self.client_instance_id),
            ("caller bundle ID", self.caller_bundle_id),
            ("caller team ID", self.caller_team_id),
            ("protocol version", self.protocol_version),
        ):
            if not value.strip():
                raise ComputerUseBrokerConfigurationError(
                    f"Computer Use {label} must not be blank"
                )
        if not 32 <= len(self.verification_capability) <= 4_096:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use verification capability must contain between "
                "32 and 4096 bytes"
            )
        if not 0 < self.request_timeout_seconds <= 60:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use RPC timeout must be between 0 and 60 seconds"
            )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> ComputerUseBrokerConfiguration | None:
        socket_path = environment.get(_SOCKET_ENV, "").strip()
        if not socket_path:
            return None

        required = {
            _INSTANCE_ENV: environment.get(_INSTANCE_ENV, "").strip(),
            _BUNDLE_ENV: environment.get(_BUNDLE_ENV, "").strip(),
            _TEAM_ENV: environment.get(_TEAM_ENV, "").strip(),
            _CAPABILITY_FILE_ENV: environment.get(
                _CAPABILITY_FILE_ENV,
                "",
            ).strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use broker configuration is incomplete: "
                + ", ".join(sorted(missing))
            )

        raw_timeout = environment.get(_TIMEOUT_ENV, "5000").strip() or "5000"
        try:
            timeout_ms = int(raw_timeout)
        except ValueError as error:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use RPC timeout must be an integer number of milliseconds"
            ) from error
        if not 1 <= timeout_ms <= 60_000:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use RPC timeout must be between 1 and 60000 milliseconds"
            )

        capability = _read_private_capability(required[_CAPABILITY_FILE_ENV])
        return cls(
            socket_path=socket_path,
            client_instance_id=required[_INSTANCE_ENV],
            caller_bundle_id=required[_BUNDLE_ENV],
            caller_team_id=required[_TEAM_ENV],
            verification_capability=capability,
            protocol_version=(
                environment.get(_PROTOCOL_ENV, "1").strip() or "1"
            ),
            request_timeout_seconds=timeout_ms / 1_000,
        )


@dataclass(frozen=True)
class ComputerUseHandshakeReceipt:
    protocol_version: str
    broker_version: str
    broker_instance_id: str
    features: tuple[str, ...]
    screen_recording: str
    accessibility: str


@dataclass(frozen=True)
class ComputerUsePermissionReceipt:
    screen_recording: str
    accessibility: str
    coordinate_fallback_enabled: bool
    secure_field_actions_allowed: bool
    observed_at_unix_ms: int


@dataclass(frozen=True)
class ComputerUseActionExecutionReceipt:
    action_id: str
    attempt: int
    status: str
    terminal_phase: str
    events: tuple[computer_pb2.ComputerActionEvent, ...]
    result: computer_pb2.ComputerActionResult | None
    error: computer_pb2.ComputerActionError | None


@dataclass(frozen=True)
class ComputerUseCancellationReceipt:
    action_id: str
    attempt: int
    cancellation_id: str
    disposition: str
    side_effect_committed: bool


@dataclass(frozen=True)
class ComputerUseSessionCancellationReceipt:
    session_id: str
    cancellation_id: str
    disposition: str
    cancelled_action_ids: tuple[str, ...]
    too_late_action_ids: tuple[str, ...]
    cancelled_at_unix_ms: int


@dataclass(frozen=True)
class ComputerUseCloseReceipt:
    session_id: str
    closed: bool
    invalidated_handle_count: int
    closed_at_unix_ms: int


@dataclass(frozen=True)
class _ComputerUseBrokerConnection:
    channel: grpc.aio.Channel
    stub: computer_pb2_grpc.ComputerUseBrokerServiceStub
    handshake: ComputerUseHandshakeReceipt
    socket_identity: tuple[int, int, int, int]
    generation: int


class ComputerUseBrokerClient:
    """Typed asynchronous client for one explicitly configured private UDS."""

    def __init__(self, configuration: ComputerUseBrokerConfiguration) -> None:
        self.configuration = configuration
        self._channel: grpc.aio.Channel | None = None
        self._stub: computer_pb2_grpc.ComputerUseBrokerServiceStub | None = None
        self._handshake: ComputerUseHandshakeReceipt | None = None
        self._socket_identity: tuple[int, int, int, int] | None = None
        self._connection_generation = 0
        self._connect_lock = asyncio.Lock()

    async def handshake(self) -> ComputerUseHandshakeReceipt:
        connection = await self._connected_connection()
        await self._validate_response_connection(connection)
        return connection.handshake

    async def get_permissions(
        self,
        *,
        authorization: computer_pb2.ControlPlaneToolAuthorization,
        deadline_unix_ms: int = 0,
    ) -> ComputerUsePermissionReceipt:
        connection = await self._connected_connection()
        try:
            response = await connection.stub.GetPermissions(
                computer_pb2.GetPermissionsRequest(
                    authorization=authorization,
                    caller_verification_capability=(
                        self.configuration.verification_capability
                    ),
                ),
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        return _permission_receipt(response)

    async def list_targets(
        self,
        *,
        authorization: computer_pb2.ControlPlaneToolAuthorization,
        deadline_unix_ms: int = 0,
    ) -> computer_pb2.ListComputerTargetsResponse:
        connection = await self._connected_connection()
        try:
            response = await connection.stub.ListTargets(
                computer_pb2.ListComputerTargetsRequest(
                    authorization=authorization,
                    caller_verification_capability=(
                        self.configuration.verification_capability
                    ),
                ),
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        if response.observed_at_unix_ms <= 0 or len(response.targets) > 128:
            raise ComputerUseBrokerProtocolError(
                "Computer Use broker returned an invalid target inventory"
            )
        serialized_targets: set[bytes] = set()
        for target in response.targets:
            if (
                not target.bundle_id.strip()
                or target.process_id <= 0
                or not target.process_launch_identity.strip()
                or target.window_id <= 0
            ):
                raise ComputerUseBrokerProtocolError(
                    "Computer Use broker returned an incomplete target identity"
                )
            serialized = target.SerializeToString(deterministic=True)
            if serialized in serialized_targets:
                raise ComputerUseBrokerProtocolError(
                    "Computer Use broker returned duplicate target identities"
                )
            serialized_targets.add(serialized)
        return response

    async def open_session(
        self,
        request: computer_pb2.OpenComputerSessionRequest,
        *,
        deadline_unix_ms: int = 0,
    ) -> computer_pb2.ComputerSessionLease:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        try:
            response = await connection.stub.OpenSession(
                request,
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        expected_identity = _open_identity_fields(request.identity)
        if (
            _open_identity_fields(response.identity) != expected_identity
            or not response.identity.session_id
            or not response.session_capability
            or response.broker_instance_id
            != connection.handshake.broker_instance_id
            or response.limits != request.limits
        ):
            raise ComputerUseBrokerProtocolError(
                "Computer Use broker returned an invalid session lease"
            )
        requested_targets = {
            target.SerializeToString(deterministic=True)
            for target in request.allowed_targets
        }
        leased_targets = {
            target.SerializeToString(deterministic=True)
            for target in response.allowed_targets
        }
        if not leased_targets or not leased_targets.issubset(requested_targets):
            raise ComputerUseBrokerProtocolError(
                "Computer Use broker widened the session target scope"
            )
        return response

    async def capture_frame(
        self,
        request: computer_pb2.CaptureFrameRequest,
        *,
        deadline_unix_ms: int = 0,
    ) -> computer_pb2.CaptureFrameResponse:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        try:
            response = await connection.stub.CaptureFrame(
                request,
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        if (
            response.identity != request.identity
            or response.actual_target != request.target
            or not response.observation_id
            or response.frame_generation <= request.expected_previous_generation
            or any(
                element.frame_generation != response.frame_generation
                for element in response.elements
            )
        ):
            raise ComputerUseBrokerProtocolError(
                "Computer Use broker returned an invalid frame observation"
            )
        return response

    async def execute_action(
        self,
        request: computer_pb2.ExecuteComputerActionRequest,
        *,
        deadline_unix_ms: int = 0,
        on_registered: Callable[[], Awaitable[None] | None] | None = None,
    ) -> ComputerUseActionExecutionReceipt:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        call = connection.stub.ExecuteAction(
            request,
            timeout=self._timeout(deadline_unix_ms),
        )
        events: list[computer_pb2.ComputerActionEvent] = []
        terminal: computer_pb2.ComputerActionEvent | None = None
        expected_sequence = 1
        try:
            async for event in call:
                await self._validate_response_connection(connection)
                if terminal is not None:
                    raise ComputerUseBrokerProtocolError(
                        "Computer Use action emitted an event after its terminal event"
                    )
                if (
                    event.identity != request.identity
                    or event.action_id != request.action_id
                    or event.attempt != request.attempt
                ):
                    raise ComputerUseBrokerProtocolError(
                        "Computer Use action event correlation mismatch"
                    )
                if event.seq != expected_sequence:
                    raise ComputerUseBrokerProtocolError(
                        "Computer Use action event sequence mismatch"
                    )
                _action_phase_name(event.phase)
                expected_sequence += 1
                events.append(event)
                if len(events) == 1 and on_registered is not None:
                    callback_result = on_registered()
                    if inspect.isawaitable(callback_result):
                        await callback_result
                if event.phase in _TERMINAL_ACTION_PHASES:
                    terminal = event
        except asyncio.CancelledError:
            call.cancel()
            raise
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error

        if terminal is None:
            raise ComputerUseBrokerProtocolError(
                "Computer Use action stream ended without a terminal event"
            )
        terminal_phase = _action_phase_name(terminal.phase)
        if terminal.HasField("result"):
            result = terminal.result
            error = None
        elif terminal.HasField("error"):
            result = None
            error = terminal.error
        else:
            result = None
            error = None
        status = terminal_phase
        return ComputerUseActionExecutionReceipt(
            action_id=request.action_id,
            attempt=request.attempt,
            status=status,
            terminal_phase=terminal_phase,
            events=tuple(events),
            result=result,
            error=error,
        )

    async def cancel_action(
        self,
        request: computer_pb2.CancelComputerActionRequest,
        *,
        deadline_unix_ms: int = 0,
    ) -> ComputerUseCancellationReceipt:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        try:
            response = await connection.stub.CancelAction(
                request,
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        if (
            response.action_id != request.action_id
            or response.attempt != request.attempt
            or response.cancellation_id != request.cancellation_id
        ):
            raise ComputerUseBrokerProtocolError(
                "Computer Use cancellation receipt correlation mismatch"
            )
        return ComputerUseCancellationReceipt(
            action_id=response.action_id,
            attempt=response.attempt,
            cancellation_id=response.cancellation_id,
            disposition=_cancellation_disposition_name(response.disposition),
            side_effect_committed=response.side_effect_committed,
        )

    async def cancel_session(
        self,
        request: computer_pb2.CancelComputerSessionRequest,
        *,
        deadline_unix_ms: int = 0,
    ) -> ComputerUseSessionCancellationReceipt:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        try:
            response = await connection.stub.CancelSession(
                request,
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        if (
            response.session_id != request.identity.session_id
            or response.cancellation_id != request.cancellation_id
        ):
            raise ComputerUseBrokerProtocolError(
                "Computer Use session cancellation receipt correlation mismatch"
            )
        return ComputerUseSessionCancellationReceipt(
            session_id=response.session_id,
            cancellation_id=response.cancellation_id,
            disposition=_session_cancellation_disposition_name(
                response.disposition
            ),
            cancelled_action_ids=tuple(response.cancelled_action_ids),
            too_late_action_ids=tuple(response.too_late_action_ids),
            cancelled_at_unix_ms=response.cancelled_at_unix_ms,
        )

    async def close_session(
        self,
        request: computer_pb2.CloseComputerSessionRequest,
        *,
        deadline_unix_ms: int = 0,
    ) -> ComputerUseCloseReceipt:
        connection = await self._connected_connection()
        request.caller_verification_capability = (
            self.configuration.verification_capability
        )
        try:
            response = await connection.stub.CloseSession(
                request,
                timeout=self._timeout(deadline_unix_ms),
            )
        except grpc.aio.AioRpcError as error:
            await self._invalidate_after_rpc_error(connection, error)
            raise _rpc_error(error) from error
        await self._validate_response_connection(connection)
        if response.session_id != request.identity.session_id:
            raise ComputerUseBrokerProtocolError(
                "Computer Use close receipt correlation mismatch"
            )
        return ComputerUseCloseReceipt(
            session_id=response.session_id,
            closed=response.closed,
            invalidated_handle_count=response.invalidated_handle_count,
            closed_at_unix_ms=response.closed_at_unix_ms,
        )

    async def close(self) -> None:
        async with self._connect_lock:
            channel = self._channel
            self._channel = None
            self._stub = None
            self._handshake = None
            self._socket_identity = None
        if channel is not None:
            await channel.close()

    async def _connected_connection(
        self,
    ) -> _ComputerUseBrokerConnection:
        await self._ensure_connected()
        assert self._stub is not None
        assert self._channel is not None
        assert self._handshake is not None
        assert self._socket_identity is not None
        return _ComputerUseBrokerConnection(
            channel=self._channel,
            stub=self._stub,
            handshake=self._handshake,
            socket_identity=self._socket_identity,
            generation=self._connection_generation,
        )

    async def _ensure_connected(self) -> None:
        async with self._connect_lock:
            if self._stub is not None:
                current_identity = _validate_private_socket(
                    self.configuration.socket_path
                )
                if current_identity == self._socket_identity:
                    return
                stale_channel = self._detach_connection_locked()
                if stale_channel is not None:
                    await stale_channel.close()
            socket_identity = _validate_private_socket(
                self.configuration.socket_path
            )
            channel = grpc.aio.insecure_channel(
                f"unix://{self.configuration.socket_path}"
            )
            try:
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=self.configuration.request_timeout_seconds,
                )
                stub = computer_pb2_grpc.ComputerUseBrokerServiceStub(channel)
                response = await stub.Handshake(
                    computer_pb2.BrokerHandshakeRequest(
                        protocol_version=self.configuration.protocol_version,
                        control_plane_instance_id=(
                            self.configuration.client_instance_id
                        ),
                        caller_bundle_id=self.configuration.caller_bundle_id,
                        caller_team_id=self.configuration.caller_team_id,
                        caller_verification_capability=(
                            self.configuration.verification_capability
                        ),
                    ),
                    timeout=self.configuration.request_timeout_seconds,
                )
                if (
                    _validate_private_socket(self.configuration.socket_path)
                    != socket_identity
                ):
                    raise ComputerUseBrokerTransportError(
                        "Computer Use broker socket identity changed during handshake"
                    )
                if response.protocol_version != self.configuration.protocol_version:
                    raise ComputerUseBrokerProtocolError(
                        "Computer Use broker protocol version mismatch"
                    )
                if not response.broker_instance_id.strip():
                    raise ComputerUseBrokerProtocolError(
                        "Computer Use broker omitted its instance identity"
                    )
                handshake = ComputerUseHandshakeReceipt(
                    protocol_version=response.protocol_version,
                    broker_version=response.broker_version,
                    broker_instance_id=response.broker_instance_id,
                    features=tuple(response.features),
                    screen_recording=_permission_state_name(
                        response.permissions.screen_recording
                    ),
                    accessibility=_permission_state_name(
                        response.permissions.accessibility
                    ),
                )
            except asyncio.TimeoutError as error:
                await channel.close()
                raise ComputerUseBrokerTransportError(
                    "Computer Use broker connection timed out"
                ) from error
            except grpc.aio.AioRpcError as error:
                await channel.close()
                raise _rpc_error(error) from error
            except BaseException:
                await channel.close()
                raise
            self._channel = channel
            self._stub = stub
            self._handshake = handshake
            self._socket_identity = socket_identity
            self._connection_generation += 1

    async def _validate_response_connection(
        self,
        expected: _ComputerUseBrokerConnection,
    ) -> None:
        channel_to_close: grpc.aio.Channel | None = None
        error: ComputerUseBrokerTransportError | None = None
        async with self._connect_lock:
            if (
                self._stub is not expected.stub
                or self._channel is not expected.channel
                or self._connection_generation != expected.generation
                or self._socket_identity != expected.socket_identity
            ):
                error = ComputerUseBrokerTransportError(
                    "Computer Use broker connection changed while the request "
                    "was in flight"
                )
            else:
                try:
                    current_identity = _validate_private_socket(
                        self.configuration.socket_path
                    )
                except ComputerUseBrokerTransportError as validation_error:
                    channel_to_close = self._detach_connection_locked()
                    error = validation_error
                else:
                    if current_identity != expected.socket_identity:
                        channel_to_close = self._detach_connection_locked()
                        error = ComputerUseBrokerTransportError(
                            "Computer Use broker socket identity changed while "
                            "the request was in flight"
                        )
        if channel_to_close is not None:
            await channel_to_close.close()
        if error is not None:
            raise error

    async def _invalidate_after_rpc_error(
        self,
        expected: _ComputerUseBrokerConnection,
        error: grpc.aio.AioRpcError,
    ) -> None:
        if error.code() not in {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.UNAUTHENTICATED,
        }:
            return
        channel_to_close: grpc.aio.Channel | None = None
        async with self._connect_lock:
            if (
                self._stub is expected.stub
                and self._channel is expected.channel
                and self._connection_generation == expected.generation
            ):
                channel_to_close = self._detach_connection_locked()
        if channel_to_close is not None:
            await channel_to_close.close()

    def _detach_connection_locked(self) -> grpc.aio.Channel | None:
        channel = self._channel
        self._channel = None
        self._stub = None
        self._handshake = None
        self._socket_identity = None
        return channel

    def _timeout(self, deadline_unix_ms: int) -> float:
        if deadline_unix_ms <= 0:
            return self.configuration.request_timeout_seconds
        remaining = (deadline_unix_ms - int(time.time() * 1_000)) / 1_000
        if remaining <= 0:
            raise ComputerUseBrokerRPCError(
                grpc.StatusCode.DEADLINE_EXCEEDED,
                "Computer Use request deadline has expired",
            )
        return min(self.configuration.request_timeout_seconds, remaining)


_TERMINAL_ACTION_PHASES = {
    computer_pb2.COMPUTER_ACTION_COMPLETED,
    computer_pb2.COMPUTER_ACTION_CANCELLED,
    computer_pb2.COMPUTER_ACTION_FAILED,
}


def _permission_receipt(
    snapshot: computer_pb2.PermissionSnapshot,
) -> ComputerUsePermissionReceipt:
    return ComputerUsePermissionReceipt(
        screen_recording=_permission_state_name(snapshot.screen_recording),
        accessibility=_permission_state_name(snapshot.accessibility),
        coordinate_fallback_enabled=snapshot.coordinate_fallback_enabled,
        secure_field_actions_allowed=snapshot.secure_field_actions_allowed,
        observed_at_unix_ms=snapshot.observed_at_unix_ms,
    )


def _permission_state_name(value: int) -> str:
    if value == computer_pb2.PERMISSION_STATE_UNSPECIFIED:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker omitted a permission state"
        )
    try:
        name = computer_pb2.PermissionState.Name(value)
    except ValueError as error:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker returned an unknown permission state"
        ) from error
    return name.removeprefix("PERMISSION_").lower()


def _action_phase_name(value: int) -> str:
    if value == computer_pb2.COMPUTER_ACTION_PHASE_UNSPECIFIED:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker omitted an action phase"
        )
    try:
        name = computer_pb2.ComputerActionPhase.Name(value)
    except ValueError as error:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker returned an unknown action phase"
        ) from error
    return name.removeprefix("COMPUTER_ACTION_").lower()


def _cancellation_disposition_name(value: int) -> str:
    if value == computer_pb2.COMPUTER_CANCELLATION_DISPOSITION_UNSPECIFIED:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker omitted a cancellation disposition"
        )
    try:
        name = computer_pb2.ComputerCancellationDisposition.Name(value)
    except ValueError as error:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker returned an unknown cancellation disposition"
        ) from error
    return name.removeprefix("COMPUTER_CANCELLATION_").lower()


def _session_cancellation_disposition_name(value: int) -> str:
    if (
        value
        == computer_pb2.COMPUTER_SESSION_CANCELLATION_DISPOSITION_UNSPECIFIED
    ):
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker omitted a session cancellation disposition"
        )
    try:
        name = computer_pb2.ComputerSessionCancellationDisposition.Name(value)
    except ValueError as error:
        raise ComputerUseBrokerProtocolError(
            "Computer Use broker returned an unknown session cancellation disposition"
        ) from error
    return name.removeprefix("COMPUTER_SESSION_CANCELLATION_").lower()


def _open_identity_fields(
    identity: computer_pb2.ComputerSessionIdentity,
) -> tuple[str, str, str, str, str]:
    return (
        identity.agent_run_id,
        identity.request_id,
        identity.tool_call_id,
        identity.branch_id,
        identity.actor_id,
    )


def _rpc_error(error: grpc.aio.AioRpcError) -> ComputerUseBrokerRPCError:
    return ComputerUseBrokerRPCError(
        error.code(),
        "Computer Use broker RPC failed",
    )


def _validate_standardized_absolute_path(
    raw_path: str,
    *,
    label: str,
    maximum_bytes: int | None = None,
) -> None:
    if not raw_path or not os.path.isabs(raw_path):
        raise ComputerUseBrokerConfigurationError(f"{label} must be absolute")
    if os.path.normpath(raw_path) != raw_path:
        raise ComputerUseBrokerConfigurationError(
            f"{label} must already be standardized"
        )
    if maximum_bytes is not None and len(raw_path.encode("utf-8")) > maximum_bytes:
        raise ComputerUseBrokerConfigurationError(f"{label} is too long")


def _validate_private_socket(socket_path: str) -> tuple[int, int, int, int]:
    _validate_standardized_absolute_path(
        socket_path,
        label="Computer Use broker socket",
        maximum_bytes=103,
    )
    parent_path = os.path.dirname(socket_path)
    try:
        parent = os.lstat(parent_path)
        socket = os.lstat(socket_path)
    except OSError as error:
        raise ComputerUseBrokerTransportError(
            "Computer Use broker socket is unavailable"
        ) from error
    if not stat.S_ISDIR(parent.st_mode):
        raise ComputerUseBrokerTransportError(
            "Computer Use broker socket parent is not a directory"
        )
    if not stat.S_ISSOCK(socket.st_mode):
        raise ComputerUseBrokerTransportError(
            "Computer Use broker path is not a Unix-domain socket"
        )
    current_user = os.geteuid()
    if parent.st_uid != current_user or socket.st_uid != current_user:
        raise ComputerUseBrokerTransportError(
            "Computer Use broker socket is not owned by the current user"
        )
    if parent.st_mode & 0o077 or socket.st_mode & 0o077:
        raise ComputerUseBrokerTransportError(
            "Computer Use broker socket permissions are not private"
        )
    return (
        parent.st_dev,
        parent.st_ino,
        socket.st_dev,
        socket.st_ino,
    )


def _read_private_capability(path: str) -> bytes:
    _validate_standardized_absolute_path(
        path,
        label="Computer Use verification capability file",
    )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ComputerUseBrokerConfigurationError(
            "Computer Use verification capability file is unavailable"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ComputerUseBrokerConfigurationError(
                "Computer Use verification capability must be a regular file"
            )
        if metadata.st_uid != os.geteuid():
            raise ComputerUseBrokerConfigurationError(
                "Computer Use verification capability has the wrong owner"
            )
        if metadata.st_mode & 0o077:
            raise ComputerUseBrokerConfigurationError(
                "Computer Use verification capability permissions are not private"
            )
        payload = os.read(descriptor, 4_097)
    finally:
        os.close(descriptor)
    if not 32 <= len(payload) <= 4_096:
        raise ComputerUseBrokerConfigurationError(
            "Computer Use verification capability must contain between "
            "32 and 4096 bytes"
        )
    return payload
