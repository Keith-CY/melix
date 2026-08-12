from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from packages.protocol.python.computer.v1 import computer_pb2
from worker.runtime.computer_use_client import (
    ComputerUseActionExecutionReceipt,
    ComputerUseBrokerClient,
    ComputerUseBrokerClientError,
    ComputerUseBrokerConfiguration,
    ComputerUseSessionCancellationReceipt,
)


COMPUTER_USE_SOURCE_ID = "computer"
COMPUTER_USE_TOOL_NAME = "computer_use"
COMPUTER_USE_OPERATOR_PROJECTION_SCHEMA_VERSION = (
    "melix.computer_use_operator_projection.v1"
)


class ComputerUseAdapterError(RuntimeError):
    code = "computer_use_adapter_error"


class ComputerUseArgumentsError(ComputerUseAdapterError):
    code = "computer_use_arguments_invalid"


class ComputerUseSessionError(ComputerUseAdapterError):
    code = "computer_use_session_invalid"


class ComputerUseApprovalError(ComputerUseAdapterError):
    code = "computer_use_approval_invalid"


class ComputerUseTombstoneCapacityError(ComputerUseAdapterError):
    code = "computer_use_tombstone_capacity_exhausted"


@dataclass(frozen=True)
class ComputerUseToolDefinition:
    source_id: str
    adapter_kind: str
    name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    schema_digest: str
    risk_class: str
    replayability: str
    annotations_untrusted: bool


@dataclass(frozen=True)
class ComputerUseAdapterResult:
    status: str
    payload: Mapping[str, Any]
    receipt: Mapping[str, Any]


@dataclass(frozen=True)
class ComputerUseAdapterCancellationReceipt:
    disposition: str
    error_code: str = ""
    side_effect_committed: bool = False


@dataclass
class _SessionState:
    lease: computer_pb2.ComputerSessionLease
    authorization: computer_pb2.ControlPlaneToolAuthorization
    authorization_issued_at_unix_ms: int
    authorization_expires_at_unix_ms: int
    latest_frame: computer_pb2.CaptureFrameResponse | None = None
    cancellation: ComputerUseSessionCancellationReceipt | None = None


@dataclass
class _ActiveAction:
    identity: computer_pb2.ComputerSessionIdentity
    session_capability: bytes
    action_id: str
    attempt: int
    authorization: computer_pb2.ControlPlaneToolAuthorization
    registered: asyncio.Event
    terminal: asyncio.Event
    cancellation: ComputerUseAdapterCancellationReceipt | None = None


@dataclass(frozen=True)
class _AuthorizationConstraints:
    artifact_root: str
    maximum_frames: int
    maximum_actions: int
    maximum_artifact_bytes: int
    idle_deadline_unix_ms: int
    absolute_deadline_unix_ms: int
    request_deadline_unix_ms: int
    issued_at_unix_ms: int
    expires_at_unix_ms: int


_TARGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "bundle_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "process_id": {"type": "integer", "minimum": 1},
        "process_launch_identity": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
        },
        "window_id": {"type": "integer", "minimum": 1},
        "window_title": {
            "type": "string",
            "maxLength": 512,
        },
        "application_name": {"type": "string", "maxLength": 256},
    },
    "required": [
        "bundle_id",
        "process_id",
        "process_launch_identity",
        "window_id",
        "window_title",
    ],
    "additionalProperties": False,
}

_ELEMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "handle_id": {"type": "string", "maxLength": 512},
        "title": {"type": "string", "maxLength": 512},
        "role": {"type": "string", "maxLength": 128},
    },
    "additionalProperties": False,
}

COMPUTER_USE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": [
                "get_permissions",
                "list_targets",
                "open_session",
                "capture_frame",
                "press_element",
                "close_session",
            ],
        },
        "allowed_targets": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": _TARGET_SCHEMA,
        },
        "session_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "target": _TARGET_SCHEMA,
        "expected_previous_generation": {"type": "integer", "minimum": 0},
        "expected_observation_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
        },
        "expected_frame_generation": {"type": "integer", "minimum": 1},
        "element": _ELEMENT_SCHEMA,
        "attempt": {"type": "integer", "minimum": 1},
        "reason": {"type": "string", "maxLength": 256},
    },
    "required": ["operation"],
    "additionalProperties": False,
}

COMPUTER_USE_SCHEMA_DIGEST = hashlib.sha256(
    json.dumps(
        {
            "name": COMPUTER_USE_TOOL_NAME,
            "description": (
                "Inspect permissions, perform operator-only window discovery, "
                "open a bounded native macOS session, "
                "capture an allowed window, perform an approved AX semantic "
                "press, or close the session. Text, key, scroll, pointer, and "
                "coordinate actions are unsupported."
            ),
            "input_schema": COMPUTER_USE_INPUT_SCHEMA,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

_DEFAULT_MAXIMUM_TOMBSTONE_RECORDS = 4_096
# The adapter uses the same fixed retry horizon as the worker runtime. It
# rejects new run/call identities at capacity instead of evicting an unexpired
# cancellation receipt that still guards a native side effect.
_DEFAULT_TOMBSTONE_RETENTION_SECONDS = 3_600.0


class ComputerUseToolAdapter:
    """Stateful tool adapter that never exposes broker capabilities to a model."""

    def __init__(
        self,
        client: ComputerUseBrokerClient,
        *,
        maximum_frames: int = 16,
        maximum_actions: int = 8,
        maximum_artifact_bytes: int = 16 * 1_024 * 1_024,
        idle_timeout_seconds: int = 60,
        session_ttl_seconds: int = 300,
        approval_ttl_seconds: int = 30,
        maximum_tombstone_records: int = (
            _DEFAULT_MAXIMUM_TOMBSTONE_RECORDS
        ),
        tombstone_retention_seconds: float = (
            _DEFAULT_TOMBSTONE_RETENTION_SECONDS
        ),
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= maximum_frames <= 64:
            raise ComputerUseArgumentsError("maximum_frames must be between 1 and 64")
        if not 1 <= maximum_actions <= 32:
            raise ComputerUseArgumentsError("maximum_actions must be between 1 and 32")
        if not 1 <= maximum_artifact_bytes <= 64 * 1_024 * 1_024:
            raise ComputerUseArgumentsError(
                "maximum_artifact_bytes must be between 1 and 67108864"
            )
        if not 1 <= idle_timeout_seconds <= 300:
            raise ComputerUseArgumentsError(
                "idle_timeout_seconds must be between 1 and 300"
            )
        if not 1 <= session_ttl_seconds <= 600:
            raise ComputerUseArgumentsError(
                "session_ttl_seconds must be between 1 and 600"
            )
        if not 1 <= approval_ttl_seconds <= 60:
            raise ComputerUseArgumentsError(
                "approval_ttl_seconds must be between 1 and 60"
            )
        if maximum_tombstone_records < 1:
            raise ComputerUseArgumentsError(
                "maximum_tombstone_records must be positive"
            )
        if (
            not math.isfinite(tombstone_retention_seconds)
            or tombstone_retention_seconds <= 0
        ):
            raise ComputerUseArgumentsError(
                "tombstone_retention_seconds must be finite and positive"
            )
        self._client = client
        self._maximum_frames = maximum_frames
        self._maximum_actions = maximum_actions
        self._maximum_artifact_bytes = maximum_artifact_bytes
        self._idle_timeout_seconds = idle_timeout_seconds
        self._session_ttl_seconds = session_ttl_seconds
        self._approval_ttl_seconds = approval_ttl_seconds
        self._maximum_tombstone_records = maximum_tombstone_records
        self._tombstone_retention_seconds = tombstone_retention_seconds
        self._monotonic_clock = monotonic_clock
        self._sessions: dict[tuple[str, str], _SessionState] = {}
        self._active_actions: dict[tuple[str, str], _ActiveAction] = {}
        self._cancellation_receipts: dict[
            tuple[str, str], ComputerUseAdapterCancellationReceipt
        ] = {}
        self._cancellation_receipt_expires_at: dict[
            tuple[str, str], float
        ] = {}
        self._cancellations_in_flight: dict[
            tuple[str, str],
            asyncio.Future[ComputerUseAdapterCancellationReceipt],
        ] = {}
        self._known_calls: dict[tuple[str, str], float] = {}
        self._known_runs: dict[str, float] = {}
        self._opening_runs: set[str] = set()
        self._cancelled_runs: dict[str, float] = {}
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    @property
    def definition(self) -> ComputerUseToolDefinition:
        return ComputerUseToolDefinition(
            source_id=COMPUTER_USE_SOURCE_ID,
            adapter_kind="computer",
            name=COMPUTER_USE_TOOL_NAME,
            title="Computer Use",
            description=(
                "Inspect permissions, perform operator-only window discovery, "
                "open a bounded native macOS session, "
                "capture an allowed window, perform an approved AX semantic "
                "press, or close the session. Text, key, scroll, pointer, and "
                "coordinate actions are unsupported."
            ),
            input_schema=COMPUTER_USE_INPUT_SCHEMA,
            schema_digest=COMPUTER_USE_SCHEMA_DIGEST,
            risk_class="computer_control",
            replayability="evidence_only",
            annotations_untrusted=True,
        )

    async def initialize(self) -> None:
        await self._client.handshake()

    async def execute(self, call, context) -> ComputerUseAdapterResult:
        if (
            call.expected_schema_digest
            and call.expected_schema_digest != COMPUTER_USE_SCHEMA_DIGEST
        ):
            return self._failure(
                operation="unknown",
                error_code="computer_use_schema_changed",
            )
        try:
            await self._admit_call_identity(context.run_id, call.call_id)
            arguments = dict(call.arguments)
            operation = _required_string(arguments, "operation")
            constraints = _authorization_constraints(context)
            if operation == "get_permissions":
                return await self._get_permissions(context, constraints)
            if operation == "list_targets":
                return await self._list_targets(context, constraints)
            if operation == "open_session":
                return await self._open_session(
                    call,
                    context,
                    arguments,
                    constraints,
                )
            if operation == "capture_frame":
                return await self._capture_frame(
                    call,
                    context,
                    arguments,
                    constraints,
                )
            if operation == "press_element":
                return await self._press_element(
                    call,
                    context,
                    arguments,
                    constraints,
                )
            if operation == "close_session":
                return await self._close_session(
                    call,
                    context,
                    arguments,
                    constraints,
                )
            raise ComputerUseArgumentsError(
                f"unsupported Computer Use operation {operation!r}"
            )
        except asyncio.CancelledError:
            raise
        except (ComputerUseAdapterError, ComputerUseBrokerClientError) as error:
            return self._failure(
                operation=str(call.arguments.get("operation", "unknown")),
                error_code=getattr(error, "code", "computer_use_failed"),
            )

    async def _admit_call_identity(self, run_id: str, call_id: str) -> None:
        key = (run_id, call_id)
        async with self._lock:
            now = self._monotonic_clock()
            self._prune_tombstones_locked(now)
            if run_id in self._cancelled_runs:
                raise ComputerUseSessionError(
                    "Computer Use run was already cancelled"
                )
            retained_runs = set(self._known_runs).union(
                self._cancelled_runs
            )
            retained_calls = self._retained_call_record_keys_locked()
            if (
                run_id not in retained_runs
                and len(retained_runs) >= self._maximum_tombstone_records
            ):
                raise ComputerUseTombstoneCapacityError(
                    "Computer Use run tombstone capacity is exhausted until "
                    "the configured retry horizon elapses"
                )
            if (
                key not in retained_calls
                and len(retained_calls) >= self._maximum_tombstone_records
            ):
                raise ComputerUseTombstoneCapacityError(
                    "Computer Use call tombstone capacity is exhausted until "
                    "the configured retry horizon elapses"
                )
            expires_at = now + self._tombstone_retention_seconds
            self._known_runs[run_id] = expires_at
            self._known_calls[key] = expires_at

    def _prune_tombstones_locked(self, now: float) -> None:
        for key, expires_at in list(
            self._cancellation_receipt_expires_at.items()
        ):
            if (
                expires_at <= now
                and key not in self._active_actions
                and key not in self._cancellations_in_flight
            ):
                self._cancellation_receipt_expires_at.pop(key, None)
                self._cancellation_receipts.pop(key, None)

        for key, expires_at in list(self._known_calls.items()):
            if (
                expires_at <= now
                and key not in self._active_actions
                and key not in self._cancellations_in_flight
            ):
                self._known_calls.pop(key, None)

        for run_id, expires_at in list(self._cancelled_runs.items()):
            if expires_at <= now and not self._run_has_live_state_locked(run_id):
                self._cancelled_runs.pop(run_id, None)

        for run_id, expires_at in list(self._known_runs.items()):
            if expires_at > now or self._run_has_live_state_locked(run_id):
                continue
            if any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._known_calls
            ):
                continue
            self._known_runs.pop(run_id, None)

    def _run_has_live_state_locked(self, run_id: str) -> bool:
        return (
            run_id in self._opening_runs
            or any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._sessions
            )
            or any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._active_actions
            )
            or any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._cancellations_in_flight
            )
        )

    def _retained_call_record_keys_locked(
        self,
    ) -> set[tuple[str, str]]:
        return (
            set(self._known_calls)
            .union(
                key
                for key in self._cancellation_receipt_expires_at
                if key[1] != "__run_cleanup__"
            )
            .union(
                key
                for key in self._cancellations_in_flight
                if key[1] != "__run_cleanup__"
            )
        )

    async def cancel(
        self,
        run_id: str,
        call_id: str,
    ) -> ComputerUseAdapterCancellationReceipt:
        action_key = (run_id, call_id)
        is_run_cleanup = call_id.startswith("__run_cleanup__:")
        record_key = (
            (run_id, "__run_cleanup__")
            if is_run_cleanup
            else action_key
        )
        pending: asyncio.Future[ComputerUseAdapterCancellationReceipt]
        leader = False
        async with self._lock:
            now = self._monotonic_clock()
            self._prune_tombstones_locked(now)
            cached = self._cancellation_receipts.get(record_key)
            if cached is not None:
                return cached
            existing_pending = self._cancellations_in_flight.get(record_key)
            if existing_pending is not None:
                pending = existing_pending
            else:
                retained_runs = set(self._known_runs).union(
                    self._cancelled_runs
                )
                retained_calls = self._retained_call_record_keys_locked()
                if (
                    run_id not in retained_runs
                    and len(retained_runs)
                    >= self._maximum_tombstone_records
                ):
                    return ComputerUseAdapterCancellationReceipt(
                        disposition="too_late",
                        error_code=ComputerUseTombstoneCapacityError.code,
                    )
                if (
                    not is_run_cleanup
                    and record_key not in retained_calls
                    and len(retained_calls)
                    >= self._maximum_tombstone_records
                ):
                    return ComputerUseAdapterCancellationReceipt(
                        disposition="too_late",
                        error_code=ComputerUseTombstoneCapacityError.code,
                    )
                expires_at = now + self._tombstone_retention_seconds
                self._known_runs.pop(run_id, None)
                self._cancelled_runs[run_id] = expires_at
                if not is_run_cleanup:
                    self._known_calls[record_key] = expires_at
                pending = asyncio.get_running_loop().create_future()
                self._cancellations_in_flight[record_key] = pending
                opening = run_id in self._opening_runs
                active = self._active_actions.get(action_key)
                session_items = [
                    (session_id, state)
                    for (candidate_run_id, session_id), state
                    in self._sessions.items()
                    if candidate_run_id == run_id
                ]
                leader = True

        if not leader:
            return await asyncio.shield(pending)

        try:
            action_receipt = await self._cancel_active_action(
                run_id,
                call_id,
                active,
            )
            session_receipts = await asyncio.gather(
                *(
                    self._cancel_session(
                        run_id=run_id,
                        session_id=session_id,
                        state=state,
                        reason=f"run cancellation for tool call {call_id}",
                    )
                    for session_id, state in session_items
                ),
                return_exceptions=True,
            )
            result = _combined_cancellation_receipt(
                action_receipt,
                session_receipts,
                opening=opening,
            )
        except BaseException:
            async with self._lock:
                if self._cancellations_in_flight.get(record_key) is pending:
                    self._cancellations_in_flight.pop(record_key, None)
                    pending.cancel()
            raise
        async with self._lock:
            expires_at = (
                self._monotonic_clock()
                + self._tombstone_retention_seconds
            )
            self._cancelled_runs[run_id] = expires_at
            self._cancellation_receipts[record_key] = result
            self._cancellation_receipt_expires_at[record_key] = expires_at
            self._known_calls.pop(record_key, None)
            if self._cancellations_in_flight.get(record_key) is pending:
                self._cancellations_in_flight.pop(record_key, None)
                pending.set_result(result)
            if (
                active is not None
                and self._active_actions.get(action_key) is active
            ):
                active.cancellation = result
        return result

    async def close(self) -> None:
        async with self._lock:
            session_items = list(self._sessions.items())
            cleanup_tasks = list(self._cleanup_tasks)
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        await asyncio.gather(
            *(
                self._cancel_session(
                    run_id=run_id,
                    session_id=session_id,
                    state=state,
                    reason="worker adapter shutdown",
                )
                for (run_id, session_id), state in session_items
            ),
            return_exceptions=True,
        )
        async with self._lock:
            self._sessions.clear()
        await self._client.close()

    async def _cancel_active_action(
        self,
        run_id: str,
        call_id: str,
        active: _ActiveAction | None,
    ) -> ComputerUseAdapterCancellationReceipt:
        if active is None:
            return ComputerUseAdapterCancellationReceipt(disposition="not_found")
        if active.cancellation is not None:
            return active.cancellation
        if active.terminal.is_set():
            return ComputerUseAdapterCancellationReceipt(
                disposition="already_terminal"
            )

        cancellation_digest = hashlib.sha256(
            f"{run_id}:{call_id}".encode()
        ).hexdigest()[:24]
        request = computer_pb2.CancelComputerActionRequest(
            identity=active.identity,
            session_capability=active.session_capability,
            action_id=active.action_id,
            attempt=active.attempt,
            cancellation_id=f"cancel-{cancellation_digest}",
            authorization=active.authorization,
        )
        timeout = min(
            1.0,
            self._client.configuration.request_timeout_seconds,
        )
        deadline = time.monotonic() + timeout
        while True:
            if active.terminal.is_set():
                return ComputerUseAdapterCancellationReceipt(
                    disposition="already_terminal"
                )
            try:
                broker_receipt = await self._client.cancel_action(request)
            except ComputerUseBrokerClientError as error:
                return ComputerUseAdapterCancellationReceipt(
                    disposition="too_late",
                    error_code=error.code,
                )
            if broker_receipt.disposition != "not_found":
                return ComputerUseAdapterCancellationReceipt(
                    disposition=broker_receipt.disposition,
                    side_effect_committed=(
                        broker_receipt.side_effect_committed
                    ),
                )
            if time.monotonic() >= deadline:
                return ComputerUseAdapterCancellationReceipt(
                    disposition="not_found"
                )
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(active.registered.wait(), timeout=0.01)

    async def _cancel_session(
        self,
        *,
        run_id: str,
        session_id: str,
        state: _SessionState,
        reason: str,
    ) -> ComputerUseSessionCancellationReceipt:
        if state.cancellation is not None:
            return state.cancellation
        cancellation_digest = hashlib.sha256(
            f"{run_id}:{session_id}".encode()
        ).hexdigest()[:24]
        receipt = await self._client.cancel_session(
            computer_pb2.CancelComputerSessionRequest(
                identity=state.lease.identity,
                session_capability=state.lease.session_capability,
                cancellation_id=f"cancel-session-{cancellation_digest}",
                reason=reason[:256],
                authorization=state.authorization,
            )
        )
        state.cancellation = receipt
        if receipt.disposition in {"accepted", "already_terminal"}:
            async with self._lock:
                current = self._sessions.get((run_id, session_id))
                if current is state:
                    self._sessions.pop((run_id, session_id), None)
        return receipt

    async def _cancel_open_when_ready(
        self,
        *,
        open_task: asyncio.Task[computer_pb2.ComputerSessionLease],
        request: computer_pb2.OpenComputerSessionRequest,
        run_id: str,
        actor_id: str,
        authorization: computer_pb2.ControlPlaneToolAuthorization,
        authorization_issued_at_unix_ms: int,
        authorization_expires_at_unix_ms: int,
    ) -> None:
        try:
            lease = await open_task
        except (ComputerUseBrokerClientError, asyncio.CancelledError):
            try:
                lease = await self._client.open_session(request)
            except (ComputerUseBrokerClientError, asyncio.CancelledError):
                return
        if (
            lease.identity.agent_run_id != run_id
            or lease.identity.actor_id != actor_id
            or not lease.identity.session_id
            or not lease.session_capability
        ):
            return
        state = _SessionState(
            lease=lease,
            authorization=authorization,
            authorization_issued_at_unix_ms=(
                authorization_issued_at_unix_ms
            ),
            authorization_expires_at_unix_ms=(
                authorization_expires_at_unix_ms
            ),
        )
        try:
            await self._cancel_session(
                run_id=run_id,
                session_id=lease.identity.session_id,
                state=state,
                reason="cancelled session-open reconciliation",
            )
        except ComputerUseBrokerClientError:
            return

    async def _get_permissions(
        self,
        context,
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        handshake = await self._client.handshake()
        permissions = await self._client.get_permissions(
            authorization=_authorization(context),
            deadline_unix_ms=_effective_request_deadline(
                context,
                constraints,
            ),
        )
        payload = {
            "operation": "get_permissions",
            "screen_recording": permissions.screen_recording,
            "accessibility": permissions.accessibility,
            "coordinate_fallback_enabled": (
                permissions.coordinate_fallback_enabled
            ),
            "secure_field_actions_allowed": (
                permissions.secure_field_actions_allowed
            ),
            "observed_at_unix_ms": permissions.observed_at_unix_ms,
            "broker_features": list(handshake.features),
            "action_surface": "ax_semantic_press_only",
            "unsupported_actions": [
                "set_text",
                "key_press",
                "scroll",
                "pointer",
                "coordinate_fallback",
            ],
            "maximum_frames": min(
                self._maximum_frames,
                constraints.maximum_frames,
            ),
            "maximum_actions": min(
                self._maximum_actions,
                constraints.maximum_actions,
            ),
            "maximum_artifact_bytes": min(
                self._maximum_artifact_bytes,
                constraints.maximum_artifact_bytes,
            ),
            "idle_timeout_seconds": self._idle_timeout_seconds,
            "absolute_timeout_seconds": self._session_ttl_seconds,
        }
        return self._success(
            operation="get_permissions",
            payload=payload,
            broker_instance_id=handshake.broker_instance_id,
        )

    async def _list_targets(
        self,
        context,
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        handshake = await self._client.handshake()
        response = await self._client.list_targets(
            authorization=_authorization(context),
            deadline_unix_ms=_effective_request_deadline(
                context,
                constraints,
            ),
        )
        return self._success(
            operation="list_targets",
            payload={
                "operation": "list_targets",
                "targets": [_target_payload(target) for target in response.targets],
                "observed_at_unix_ms": response.observed_at_unix_ms,
            },
            broker_instance_id=handshake.broker_instance_id,
        )

    async def _open_session(
        self,
        call,
        context,
        arguments: Mapping[str, Any],
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        if not context.session_id.strip() or not context.branch_id.strip():
            raise ComputerUseSessionError(
                "Computer Use requires session and branch identity"
            )
        if not call.idempotency_key.strip():
            raise ComputerUseSessionError(
                "Computer Use session requires an idempotency key"
            )
        raw_targets = arguments.get("allowed_targets")
        if not isinstance(raw_targets, list) or not 1 <= len(raw_targets) <= 16:
            raise ComputerUseArgumentsError(
                "allowed_targets must contain between 1 and 16 targets"
            )
        targets = [_target_from_mapping(value) for value in raw_targets]
        target_keys = [_target_key(target) for target in targets]
        if len(set(target_keys)) != len(target_keys):
            raise ComputerUseArgumentsError("allowed_targets contains duplicates")

        now_ms = int(time.time() * 1_000)
        absolute_deadline = min(
            now_ms + self._session_ttl_seconds * 1_000,
            constraints.absolute_deadline_unix_ms,
        )
        idle_deadline = min(
            now_ms + self._idle_timeout_seconds * 1_000,
            constraints.idle_deadline_unix_ms,
        )
        if context.deadline_unix_ms:
            absolute_deadline = min(absolute_deadline, context.deadline_unix_ms)
            idle_deadline = min(idle_deadline, context.deadline_unix_ms)
        if absolute_deadline <= now_ms:
            raise ComputerUseSessionError("Computer Use session deadline expired")
        if idle_deadline <= now_ms:
            raise ComputerUseSessionError(
                "Computer Use idle deadline expired"
            )
        idle_deadline = min(idle_deadline, absolute_deadline)
        identity = computer_pb2.ComputerSessionIdentity(
            agent_run_id=context.run_id,
            request_id=call.call_id,
            tool_call_id=call.call_id,
            branch_id=context.branch_id,
            actor_id=context.actor_id,
        )
        authorization = _authorization(context)
        request = computer_pb2.OpenComputerSessionRequest(
            identity=identity,
            allowed_targets=targets,
            artifact_root=constraints.artifact_root,
            limits=computer_pb2.ComputerSessionLimits(
                maximum_frames=min(
                    self._maximum_frames,
                    constraints.maximum_frames,
                ),
                maximum_actions=min(
                    self._maximum_actions,
                    constraints.maximum_actions,
                ),
                maximum_artifact_bytes=min(
                    self._maximum_artifact_bytes,
                    constraints.maximum_artifact_bytes,
                ),
                idle_deadline_unix_ms=idle_deadline,
                absolute_deadline_unix_ms=absolute_deadline,
            ),
            idempotency_key=call.idempotency_key,
            authorization=authorization,
        )
        async with self._lock:
            if context.run_id in self._cancelled_runs:
                raise ComputerUseSessionError(
                    "Computer Use run was already cancelled"
                )
            self._opening_runs.add(context.run_id)
        open_task: asyncio.Task[computer_pb2.ComputerSessionLease] | None = None
        try:
            handshake = await self._client.handshake()
            open_task = asyncio.create_task(
                self._client.open_session(
                    request,
                    deadline_unix_ms=_effective_request_deadline(
                        context,
                        constraints,
                    ),
                )
            )
            try:
                lease = await asyncio.shield(open_task)
            except asyncio.CancelledError:
                async with self._lock:
                    self._known_runs.pop(context.run_id, None)
                    self._cancelled_runs[context.run_id] = (
                        self._monotonic_clock()
                        + self._tombstone_retention_seconds
                    )
                cleanup = asyncio.create_task(
                    self._cancel_open_when_ready(
                        open_task=open_task,
                        request=request,
                        run_id=context.run_id,
                        actor_id=context.actor_id,
                        authorization=authorization,
                        authorization_issued_at_unix_ms=(
                            constraints.issued_at_unix_ms
                        ),
                        authorization_expires_at_unix_ms=(
                            constraints.expires_at_unix_ms
                        ),
                    )
                )
                self._cleanup_tasks.add(cleanup)
                cleanup.add_done_callback(self._cleanup_tasks.discard)
                raise
            if (
                lease.identity.agent_run_id != context.run_id
                or lease.identity.actor_id != context.actor_id
                or not lease.identity.session_id
                or not lease.session_capability
            ):
                raise ComputerUseSessionError(
                    "Computer Use broker returned an invalid session lease"
                )
            state = _SessionState(
                lease=lease,
                authorization=authorization,
                authorization_issued_at_unix_ms=(
                    constraints.issued_at_unix_ms
                ),
                authorization_expires_at_unix_ms=(
                    constraints.expires_at_unix_ms
                ),
            )
            async with self._lock:
                cancelled = context.run_id in self._cancelled_runs
                if not cancelled:
                    self._sessions[
                        (context.run_id, lease.identity.session_id)
                    ] = state
            if cancelled:
                await self._cancel_session(
                    run_id=context.run_id,
                    session_id=lease.identity.session_id,
                    state=state,
                    reason="run cancelled while opening Computer Use session",
                )
                raise ComputerUseSessionError(
                    "Computer Use run was cancelled while opening a session"
                )
        finally:
            async with self._lock:
                self._opening_runs.discard(context.run_id)
        return self._success(
            operation="open_session",
            broker_instance_id=handshake.broker_instance_id,
            session_id=lease.identity.session_id,
            payload={
                "operation": "open_session",
                "session_id": lease.identity.session_id,
                "broker_instance_id": lease.broker_instance_id,
                "action_surface": "ax_semantic_press_only",
                "allowed_targets": [_target_payload(target) for target in lease.allowed_targets],
                "maximum_frames": lease.limits.maximum_frames,
                "maximum_actions": lease.limits.maximum_actions,
                "maximum_artifact_bytes": (
                    lease.limits.maximum_artifact_bytes
                ),
                "idle_deadline_unix_ms": (
                    lease.limits.idle_deadline_unix_ms
                ),
                "absolute_deadline_unix_ms": (
                    lease.limits.absolute_deadline_unix_ms
                ),
                "opened_at_unix_ms": lease.opened_at_unix_ms,
            },
        )

    async def _capture_frame(
        self,
        call,
        context,
        arguments: Mapping[str, Any],
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        session_id = _required_string(arguments, "session_id")
        state = await self._session(context, session_id)
        target = _target_from_mapping(arguments.get("target"))
        if _target_key(target) not in {
            _target_key(item) for item in state.lease.allowed_targets
        }:
            raise ComputerUseSessionError("capture target is outside the session")
        expected_previous_generation = _optional_integer(
            arguments,
            "expected_previous_generation",
            default=(
                state.latest_frame.frame_generation
                if state.latest_frame is not None
                else 0
            ),
            minimum=0,
            maximum=(1 << 64) - 1,
        )
        effective_deadline = _effective_request_deadline(
            context,
            constraints,
        )
        response = await self._client.capture_frame(
            computer_pb2.CaptureFrameRequest(
                identity=state.lease.identity,
                session_capability=state.lease.session_capability,
                target=target,
                capture_id=f"capture-{call.call_id}",
                expected_previous_generation=expected_previous_generation,
                deadline_unix_ms=effective_deadline,
                authorization=_authorization(context),
            ),
            deadline_unix_ms=effective_deadline,
        )
        if response.identity.session_id != session_id:
            raise ComputerUseSessionError("capture response crossed session scope")
        await self._promote_session_authorization(
            context,
            session_id,
            state,
            constraints,
        )
        state.latest_frame = response
        return self._success(
            operation="capture_frame",
            session_id=session_id,
            payload={
                "operation": "capture_frame",
                "session_id": session_id,
                "actual_target": _target_payload(response.actual_target),
                "observation_id": response.observation_id,
                "frame_generation": response.frame_generation,
                "frame": _artifact_payload(response.frame),
                "elements": [_element_payload(element) for element in response.elements],
                "evidence": _opaque_evidence(response.evidence_receipt_json),
            },
        )

    async def _press_element(
        self,
        call,
        context,
        arguments: Mapping[str, Any],
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        if context.admission_state not in {"approved", "allow"}:
            raise ComputerUseApprovalError(
                "Computer Use semantic actions require an exact approval or policy grant"
            )
        if not context.approval_grant_digest or not context.policy_revision:
            raise ComputerUseApprovalError(
                "Computer Use approval binding is incomplete"
            )
        if not call.idempotency_key.strip():
            raise ComputerUseArgumentsError(
                "Computer Use action requires an idempotency key"
            )
        session_id = _required_string(arguments, "session_id")
        state = await self._session(context, session_id)
        target = _target_from_mapping(arguments.get("target"))
        expected_observation_id = _required_string(
            arguments,
            "expected_observation_id",
        )
        expected_generation = _required_integer(
            arguments,
            "expected_frame_generation",
            minimum=1,
            maximum=(1 << 64) - 1,
        )
        if state.latest_frame is None or (
            state.latest_frame.observation_id != expected_observation_id
            or state.latest_frame.frame_generation != expected_generation
            or _target_key(state.latest_frame.actual_target) != _target_key(target)
        ):
            raise ComputerUseSessionError(
                "Computer Use action requires the latest exact frame"
            )
        requested_element = _element_from_mapping(
            arguments.get("element"),
            frame_generation=expected_generation,
        )
        matching_elements = [
            element
            for element in state.latest_frame.elements
            if _element_matches(element, requested_element)
        ]
        if len(matching_elements) != 1:
            raise ComputerUseSessionError(
                "Computer Use action requires one exact element from the latest frame"
            )
        element = matching_elements[0]
        if element.secure:
            raise ComputerUseApprovalError(
                "Computer Use refuses secure-field interaction"
            )
        if not element.enabled:
            raise ComputerUseSessionError(
                "Computer Use refuses disabled elements"
            )
        attempt = _optional_integer(
            arguments,
            "attempt",
            default=1,
            minimum=1,
            maximum=(1 << 64) - 1,
        )
        action_digest = computer_action_digest(
            session_id=session_id,
            action_id=call.call_id,
            idempotency_key=call.idempotency_key,
            target=target,
            expected_observation_id=expected_observation_id,
            expected_frame_generation=expected_generation,
            element=element,
        )
        now_ms = int(time.time() * 1_000)
        effective_deadline = _effective_request_deadline(
            context,
            constraints,
        )
        approval_expiry = min(
            now_ms + self._approval_ttl_seconds * 1_000,
            effective_deadline,
        )
        if approval_expiry <= now_ms:
            raise ComputerUseApprovalError("Computer Use approval has expired")

        request = computer_pb2.ExecuteComputerActionRequest(
            identity=state.lease.identity,
            session_capability=state.lease.session_capability,
            target=target,
            action_id=call.call_id,
            attempt=attempt,
            idempotency_key=call.idempotency_key,
            expected_observation_id=expected_observation_id,
            expected_frame_generation=expected_generation,
            deadline_unix_ms=effective_deadline,
            approval=computer_pb2.ApprovalGrant(
                approval_id=context.approval_grant_digest,
                action_digest=action_digest,
                policy_hash=context.policy_revision,
                approved_at_unix_ms=now_ms,
                expires_at_unix_ms=approval_expiry,
                actor_id=context.actor_id,
                scope=f"{context.run_id}:{call.call_id}",
            ),
            authorization=_authorization(context),
            press_element=computer_pb2.PressElementAction(element=element),
        )
        active = _ActiveAction(
            identity=state.lease.identity,
            session_capability=state.lease.session_capability,
            action_id=call.call_id,
            attempt=attempt,
            authorization=_authorization(context),
            registered=asyncio.Event(),
            terminal=asyncio.Event(),
        )
        key = (context.run_id, call.call_id)
        async with self._lock:
            self._active_actions[key] = active
        execution: ComputerUseActionExecutionReceipt | None = None
        try:
            execution = await self._client.execute_action(
                request,
                deadline_unix_ms=effective_deadline,
                on_registered=active.registered.set,
            )
            await self._promote_session_authorization(
                context,
                session_id,
                state,
                constraints,
            )
        except BaseException:
            # Once the broker has admitted the action, a lost terminal stream
            # cannot prove that AXPress stayed before its commit point. Keep a
            # conservative receipt for a concurrent Stop instead of projecting
            # the transport failure as side-effect-free.
            if active.cancellation is None:
                active.cancellation = ComputerUseAdapterCancellationReceipt(
                    disposition="already_terminal",
                    side_effect_committed=active.registered.is_set(),
                )
            raise
        finally:
            if execution is not None and active.cancellation is None:
                active.cancellation = ComputerUseAdapterCancellationReceipt(
                    disposition="already_terminal",
                    side_effect_committed=(
                        self._execution_may_have_side_effect(execution)
                    ),
                )
            active.terminal.set()
            async with self._lock:
                if self._active_actions.get(key) is active:
                    self._active_actions.pop(key, None)
        return self._action_result(session_id, execution)

    @staticmethod
    def _execution_may_have_side_effect(
        execution: ComputerUseActionExecutionReceipt,
    ) -> bool:
        commit_or_later = {
            computer_pb2.COMPUTER_ACTION_COMMIT_STARTED,
            computer_pb2.COMPUTER_ACTION_COMMITTED,
            computer_pb2.COMPUTER_ACTION_AFTER_OBSERVATION,
            computer_pb2.COMPUTER_ACTION_COMPLETED,
        }
        return any(
            event.phase in commit_or_later
            for event in execution.events
        )

    async def _close_session(
        self,
        call,
        context,
        arguments: Mapping[str, Any],
        constraints: _AuthorizationConstraints,
    ) -> ComputerUseAdapterResult:
        session_id = _required_string(arguments, "session_id")
        state = await self._session(context, session_id)
        reason = str(arguments.get("reason", "tool_requested_close")).strip()
        if not reason:
            reason = "tool_requested_close"
        receipt = await self._client.close_session(
            computer_pb2.CloseComputerSessionRequest(
                identity=state.lease.identity,
                session_capability=state.lease.session_capability,
                reason=reason[:256],
                authorization=_authorization(context),
                close_id=f"close-{call.call_id}",
            ),
            deadline_unix_ms=_effective_request_deadline(
                context,
                constraints,
            ),
        )
        if not receipt.closed:
            raise ComputerUseSessionError(
                "Computer Use broker did not close the requested session"
            )
        async with self._lock:
            self._sessions.pop((context.run_id, session_id), None)
        return self._success(
            operation="close_session",
            session_id=session_id,
            payload={
                "operation": "close_session",
                "session_id": receipt.session_id,
                "closed": receipt.closed,
                "invalidated_handle_count": receipt.invalidated_handle_count,
                "closed_at_unix_ms": receipt.closed_at_unix_ms,
            },
        )

    async def _session(
        self,
        context,
        session_id: str,
    ) -> _SessionState:
        async with self._lock:
            state = self._sessions.get((context.run_id, session_id))
            if state is None:
                raise ComputerUseSessionError(
                    "Computer Use session was not found"
                )
            if (
                state.lease.identity.agent_run_id != context.run_id
                or state.lease.identity.actor_id != context.actor_id
            ):
                raise ComputerUseSessionError(
                    "Computer Use session scope mismatch"
                )
            return state

    async def _promote_session_authorization(
        self,
        context,
        session_id: str,
        state: _SessionState,
        constraints: _AuthorizationConstraints,
    ) -> None:
        authorization = _authorization(context)
        async with self._lock:
            current = self._sessions.get((context.run_id, session_id))
            if current is not state:
                return
            # Retain only a strictly newer signed authorization after the
            # broker accepted the exact same-owner session call. Rejected,
            # delayed older, and equal-freshness calls must not poison the
            # revocation grant retained for Stop and shutdown cleanup.
            candidate_freshness = (
                constraints.issued_at_unix_ms,
                constraints.expires_at_unix_ms,
            )
            retained_freshness = (
                state.authorization_issued_at_unix_ms,
                state.authorization_expires_at_unix_ms,
            )
            if candidate_freshness > retained_freshness:
                state.authorization = authorization
                state.authorization_issued_at_unix_ms = (
                    constraints.issued_at_unix_ms
                )
                state.authorization_expires_at_unix_ms = (
                    constraints.expires_at_unix_ms
                )

    def _action_result(
        self,
        session_id: str,
        execution: ComputerUseActionExecutionReceipt,
    ) -> ComputerUseAdapterResult:
        payload: dict[str, Any] = {
            "operation": "press_element",
            "session_id": session_id,
            "action_id": execution.action_id,
            "attempt": execution.attempt,
            "status": execution.status,
            "terminal_phase": execution.terminal_phase,
            "events": [
                {
                    "seq": event.seq,
                    "phase": computer_pb2.ComputerActionPhase.Name(
                        event.phase
                    ).removeprefix("COMPUTER_ACTION_").lower(),
                    "emitted_at_unix_ms": event.emitted_at_unix_ms,
                }
                for event in execution.events
            ],
        }
        if execution.result is not None:
            payload["result"] = {
                "status": execution.result.status,
                "requested_target": _target_payload(
                    execution.result.requested_target
                ),
                "actual_target": _target_payload(execution.result.actual_target),
                "before_observation_id": (
                    execution.result.before_observation_id
                ),
                "after_observation_id": execution.result.after_observation_id,
                "artifacts": [
                    _artifact_payload(artifact)
                    for artifact in execution.result.artifacts
                ],
                "adapter_kind": execution.result.adapter_kind,
                "action_mode": execution.result.action_mode,
                "evidence": _opaque_evidence(
                    execution.result.evidence_receipt_json
                ),
            }
        if execution.error is not None:
            payload["error"] = {
                "code": execution.error.code,
                "retriable": execution.error.retriable,
            }
        receipt = {
            "schema_version": "melix.computer_use_adapter_receipt.v1",
            "adapter_kind": "computer",
            "source_id": COMPUTER_USE_SOURCE_ID,
            "operation": "press_element",
            "session_id": session_id,
            "action_id": execution.action_id,
            "attempt": execution.attempt,
            "status": execution.status,
            "terminal_phase": execution.terminal_phase,
            "event_count": len(execution.events),
            "replayability": "evidence_only",
            "operator_projection_schema_version": (
                COMPUTER_USE_OPERATOR_PROJECTION_SCHEMA_VERSION
            ),
            "operator_projection": _operator_projection(
                "press_element",
                payload,
            ),
        }
        return ComputerUseAdapterResult(
            status=execution.status,
            payload=payload,
            receipt=receipt,
        )

    def _success(
        self,
        *,
        operation: str,
        payload: Mapping[str, Any],
        broker_instance_id: str = "",
        session_id: str = "",
    ) -> ComputerUseAdapterResult:
        return ComputerUseAdapterResult(
            status="completed",
            payload=payload,
            receipt={
                "schema_version": "melix.computer_use_adapter_receipt.v1",
                "adapter_kind": "computer",
                "source_id": COMPUTER_USE_SOURCE_ID,
                "operation": operation,
                "status": "completed",
                "broker_instance_id": broker_instance_id,
                "session_id": session_id,
                "replayability": "evidence_only",
                "operator_projection_schema_version": (
                    COMPUTER_USE_OPERATOR_PROJECTION_SCHEMA_VERSION
                ),
                "operator_projection": _operator_projection(
                    operation,
                    payload,
                ),
            },
        )

    def _failure(
        self,
        *,
        operation: str,
        error_code: str,
    ) -> ComputerUseAdapterResult:
        return ComputerUseAdapterResult(
            status="failed",
            payload={
                "operation": operation,
                "failure_stage": "computer_use",
                "error_code": error_code,
            },
            receipt={
                "schema_version": "melix.computer_use_adapter_receipt.v1",
                "adapter_kind": "computer",
                "source_id": COMPUTER_USE_SOURCE_ID,
                "operation": operation,
                "status": "failed",
                "error_code": error_code,
                "replayability": "evidence_only",
            },
        )


def configured_computer_use_adapter(
    environment: Mapping[str, str],
) -> ComputerUseToolAdapter | None:
    configuration = ComputerUseBrokerConfiguration.from_environment(environment)
    if configuration is None:
        return None
    return ComputerUseToolAdapter(ComputerUseBrokerClient(configuration))


def _combined_cancellation_receipt(
    action_receipt: ComputerUseAdapterCancellationReceipt,
    session_receipts: list[
        ComputerUseSessionCancellationReceipt | BaseException
    ],
    *,
    opening: bool = False,
) -> ComputerUseAdapterCancellationReceipt:
    dispositions = [action_receipt.disposition]
    side_effect_committed = action_receipt.side_effect_committed
    error_code = action_receipt.error_code
    for receipt in session_receipts:
        if isinstance(receipt, BaseException):
            dispositions.append("too_late")
            error_code = getattr(
                receipt,
                "code",
                "computer_session_cancellation_failed",
            )
            continue
        dispositions.append(receipt.disposition)
        side_effect_committed = side_effect_committed or bool(
            receipt.too_late_action_ids
        )

    if "too_late" in dispositions or "scope_mismatch" in dispositions:
        disposition = "too_late"
    elif "accepted" in dispositions:
        disposition = "accepted"
    elif opening:
        disposition = "accepted"
    elif "already_terminal" in dispositions:
        disposition = "already_terminal"
    else:
        disposition = "not_found"
    return ComputerUseAdapterCancellationReceipt(
        disposition=disposition,
        error_code=error_code,
        side_effect_committed=side_effect_committed,
    )


def computer_action_digest(
    *,
    session_id: str,
    action_id: str,
    idempotency_key: str,
    target: computer_pb2.TargetIdentity,
    expected_observation_id: str,
    expected_frame_generation: int,
    element: computer_pb2.ElementHandle,
) -> str:
    payload = {
        "schemaVersion": "melix.computer_action.v1",
        "sessionID": session_id,
        "actionID": action_id,
        "idempotencyKey": idempotency_key,
        "target": {
            "bundleIdentifier": target.bundle_id,
            "processIdentifier": target.process_id,
            "processLaunchIdentity": target.process_launch_identity,
            "windowID": target.window_id,
            "windowTitle": target.window_title,
        },
        "expectedFrameID": expected_observation_id,
        "expectedFrameGeneration": expected_frame_generation,
        "action": {
            "press": {
                "_0": {
                    "element": {
                        "accessibilityIdentifier": element.handle_id,
                        "title": element.title,
                        "role": element.role,
                    }
                }
            }
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_from_mapping(value: Any) -> computer_pb2.TargetIdentity:
    if not isinstance(value, Mapping):
        raise ComputerUseArgumentsError("Computer Use target must be an object")
    return computer_pb2.TargetIdentity(
        bundle_id=_required_string(value, "bundle_id", maximum_length=256),
        process_id=_required_integer(
            value,
            "process_id",
            minimum=1,
            maximum=(1 << 31) - 1,
        ),
        process_launch_identity=_required_string(
            value,
            "process_launch_identity",
            maximum_length=256,
        ),
        window_id=_required_integer(
            value,
            "window_id",
            minimum=1,
            maximum=(1 << 32) - 1,
        ),
        window_title=_optional_string(
            value,
            "window_title",
            maximum_length=512,
        ),
        application_name=_optional_string(
            value,
            "application_name",
            maximum_length=256,
        ),
    )


def _element_from_mapping(
    value: Any,
    *,
    frame_generation: int,
) -> computer_pb2.ElementHandle:
    if not isinstance(value, Mapping):
        raise ComputerUseArgumentsError("Computer Use element must be an object")
    handle_id = str(value.get("handle_id", "")).strip()
    title = str(value.get("title", "")).strip()
    role = str(value.get("role", "")).strip()
    if not handle_id and not title:
        raise ComputerUseArgumentsError(
            "Computer Use element requires a handle_id or exact title"
        )
    if max(len(handle_id), len(title)) > 512 or len(role) > 128:
        raise ComputerUseArgumentsError("Computer Use element fields are too long")
    return computer_pb2.ElementHandle(
        handle_id=handle_id,
        frame_generation=frame_generation,
        role=role,
        title=title,
        secure=False,
        enabled=True,
    )


def _target_key(
    target: computer_pb2.TargetIdentity,
) -> tuple[str, int, str, int, str]:
    return (
        target.bundle_id,
        target.process_id,
        target.process_launch_identity,
        target.window_id,
        target.window_title,
    )


def _element_matches(
    observed: computer_pb2.ElementHandle,
    requested: computer_pb2.ElementHandle,
) -> bool:
    return (
        observed.frame_generation == requested.frame_generation
        and (
            not requested.handle_id
            or observed.handle_id == requested.handle_id
        )
        and (not requested.title or observed.title == requested.title)
        and (not requested.role or observed.role == requested.role)
    )


def _target_payload(target: computer_pb2.TargetIdentity) -> dict[str, Any]:
    return {
        "bundle_id": target.bundle_id,
        "process_id": target.process_id,
        "process_launch_identity": target.process_launch_identity,
        "window_id": target.window_id,
        "window_title": target.window_title,
        "application_name": target.application_name,
    }


def _operator_projection(
    operation: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the bounded typed subset that may drive operator UI state."""

    projection: dict[str, Any] = {"operation": operation}
    if operation == "get_permissions":
        _copy_projection_fields(
            payload,
            projection,
            (
                "screen_recording",
                "accessibility",
                "observed_at_unix_ms",
                "maximum_frames",
                "maximum_actions",
                "maximum_artifact_bytes",
                "idle_timeout_seconds",
                "absolute_timeout_seconds",
            ),
        )
    elif operation == "list_targets":
        targets = payload.get("targets")
        if isinstance(targets, list):
            projection["targets"] = [
                _operator_target_projection(target)
                for target in targets
                if isinstance(target, Mapping)
            ]
        _copy_projection_fields(
            payload,
            projection,
            ("observed_at_unix_ms",),
        )
    elif operation == "open_session":
        _copy_projection_fields(
            payload,
            projection,
            (
                "session_id",
                "maximum_frames",
                "maximum_actions",
                "maximum_artifact_bytes",
                "idle_deadline_unix_ms",
                "absolute_deadline_unix_ms",
                "opened_at_unix_ms",
            ),
        )
        allowed_targets = payload.get("allowed_targets")
        if isinstance(allowed_targets, list):
            projection["allowed_targets"] = [
                _operator_target_projection(target)
                for target in allowed_targets
                if isinstance(target, Mapping)
            ]
    elif operation == "capture_frame":
        _copy_projection_fields(
            payload,
            projection,
            ("session_id", "frame_generation"),
        )
        actual_target = payload.get("actual_target")
        if isinstance(actual_target, Mapping):
            projection["actual_target"] = _operator_target_projection(
                actual_target
            )
    elif operation == "press_element":
        _copy_projection_fields(
            payload,
            projection,
            (
                "session_id",
                "action_id",
                "attempt",
                "status",
                "terminal_phase",
            ),
        )
        result = payload.get("result")
        if isinstance(result, Mapping):
            trusted_result: dict[str, Any] = {}
            _copy_projection_fields(
                result,
                trusted_result,
                ("status",),
            )
            actual_target = result.get("actual_target")
            if isinstance(actual_target, Mapping):
                trusted_result["actual_target"] = (
                    _operator_target_projection(actual_target)
                )
            projection["result"] = trusted_result
    elif operation == "close_session":
        _copy_projection_fields(
            payload,
            projection,
            ("session_id", "closed", "closed_at_unix_ms"),
        )
    return projection


def _copy_projection_fields(
    source: Mapping[str, Any],
    destination: dict[str, Any],
    field_names: tuple[str, ...],
) -> None:
    for field_name in field_names:
        if field_name in source:
            destination[field_name] = source[field_name]


def _operator_target_projection(
    target: Mapping[str, Any],
) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    _copy_projection_fields(
        target,
        projection,
        (
            "bundle_id",
            "process_id",
            "process_launch_identity",
            "window_id",
            "window_title",
            "application_name",
        ),
    )
    return projection


def _element_payload(element: computer_pb2.ElementHandle) -> dict[str, Any]:
    return {
        "handle_id": element.handle_id,
        "frame_generation": element.frame_generation,
        "role": element.role,
        "title": element.title,
        "secure": element.secure,
        "enabled": element.enabled,
    }


def _artifact_payload(artifact: computer_pb2.ArtifactReference) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "relative_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "media_type": artifact.media_type,
        "byte_length": artifact.byte_length,
        "width": artifact.width,
        "height": artifact.height,
        "redaction": _opaque_evidence(artifact.redaction_receipt_json),
    }


def _opaque_evidence(raw_value: str) -> dict[str, Any]:
    encoded = raw_value.encode("utf-8")
    return {
        "present": bool(raw_value),
        "byte_length": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest() if encoded else "",
    }


def _artifact_namespace(run_id: str) -> str:
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:32].strip("_")
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    return f"agent-{safe_prefix or 'run'}-{digest}"


def _authorization_constraints(context) -> _AuthorizationConstraints:
    raw_payload = context.control_plane_authorization_payload
    if not raw_payload or len(raw_payload) > 65_536:
        raise ComputerUseApprovalError(
            "Computer Use authorization payload is missing or too large"
        )
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComputerUseApprovalError(
            "Computer Use authorization payload is malformed"
        ) from error
    if not isinstance(payload, dict):
        raise ComputerUseApprovalError(
            "Computer Use authorization payload must be an object"
        )
    if (
        payload.get("schema_version")
        != "melix.computer.tool-authorization.v2"
        or payload.get("key_id")
        != context.control_plane_authorization_key_id
        or payload.get("run_id") != context.run_id
        or payload.get("session_id") != context.session_id
        or payload.get("branch_id") != context.branch_id
        or payload.get("actor_id") != context.actor_id
        or payload.get("source_id") != COMPUTER_USE_SOURCE_ID
        or payload.get("tool_name") != COMPUTER_USE_TOOL_NAME
    ):
        raise ComputerUseApprovalError(
            "Computer Use authorization payload does not match the execution context"
        )

    artifact_root = payload.get("artifact_root")
    if (
        not isinstance(artifact_root, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", artifact_root)
        or artifact_root != _artifact_namespace(context.run_id)
    ):
        raise ComputerUseApprovalError(
            "Computer Use authorization artifact scope is invalid"
        )

    maximum_frames = _authorization_integer(payload, "maximum_frames")
    maximum_actions = _authorization_integer(payload, "maximum_actions")
    maximum_artifact_bytes = _authorization_integer(
        payload,
        "maximum_artifact_bytes",
    )
    issued_at_unix_ms = _authorization_integer(payload, "issued_at_unix_ms")
    expires_at_unix_ms = _authorization_integer(payload, "expires_at_unix_ms")
    idle_deadline_unix_ms = _authorization_integer(
        payload,
        "idle_deadline_unix_ms",
    )
    absolute_deadline_unix_ms = _authorization_integer(
        payload,
        "absolute_deadline_unix_ms",
    )
    request_deadline_unix_ms = _authorization_integer(
        payload,
        "request_deadline_unix_ms",
    )
    if (
        not 1 <= maximum_frames <= 64
        or not 1 <= maximum_actions <= 32
        or not 1 <= maximum_artifact_bytes <= 64 * 1_024 * 1_024
        or not 1_000
        <= idle_deadline_unix_ms - issued_at_unix_ms
        <= 300_000
        or not 1_000
        <= absolute_deadline_unix_ms - issued_at_unix_ms
        <= 600_000
        or idle_deadline_unix_ms > absolute_deadline_unix_ms
        or request_deadline_unix_ms != expires_at_unix_ms
        or not 1_000 <= expires_at_unix_ms - issued_at_unix_ms <= 60_000
        or (
            context.deadline_unix_ms > 0
            and request_deadline_unix_ms > context.deadline_unix_ms
        )
    ):
        raise ComputerUseApprovalError(
            "Computer Use authorization constraints are invalid"
        )
    return _AuthorizationConstraints(
        artifact_root=artifact_root,
        maximum_frames=maximum_frames,
        maximum_actions=maximum_actions,
        maximum_artifact_bytes=maximum_artifact_bytes,
        idle_deadline_unix_ms=idle_deadline_unix_ms,
        absolute_deadline_unix_ms=absolute_deadline_unix_ms,
        request_deadline_unix_ms=request_deadline_unix_ms,
        issued_at_unix_ms=issued_at_unix_ms,
        expires_at_unix_ms=expires_at_unix_ms,
    )


def _authorization_integer(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ComputerUseApprovalError(
            f"Computer Use authorization {field} must be an integer"
        )
    return value


def _effective_request_deadline(
    context,
    constraints: _AuthorizationConstraints,
) -> int:
    deadline = constraints.request_deadline_unix_ms
    if context.deadline_unix_ms > 0:
        deadline = min(deadline, context.deadline_unix_ms)
    if deadline <= int(time.time() * 1_000):
        raise ComputerUseApprovalError(
            "Computer Use authorization deadline has expired"
        )
    return deadline


def _authorization(context) -> computer_pb2.ControlPlaneToolAuthorization:
    if (
        not context.control_plane_authorization_key_id
        or context.control_plane_authorization_algorithm != "ed25519"
        or not context.control_plane_authorization_payload
        or not context.control_plane_authorization_signature
    ):
        raise ComputerUseApprovalError(
            "Computer Use requires a signed control-plane authorization"
        )
    return computer_pb2.ControlPlaneToolAuthorization(
        key_id=context.control_plane_authorization_key_id,
        algorithm=context.control_plane_authorization_algorithm,
        signed_payload=context.control_plane_authorization_payload,
        signature=context.control_plane_authorization_signature,
    )


def _required_string(
    value: Mapping[str, Any],
    field: str,
    *,
    maximum_length: int = 256,
) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ComputerUseArgumentsError(f"{field} must be a non-empty string")
    normalized = raw.strip()
    if len(normalized) > maximum_length:
        raise ComputerUseArgumentsError(f"{field} is too long")
    return normalized


def _optional_string(
    value: Mapping[str, Any],
    field: str,
    *,
    maximum_length: int,
) -> str:
    raw = value.get(field, "")
    if not isinstance(raw, str):
        raise ComputerUseArgumentsError(f"{field} must be a string")
    normalized = raw.strip()
    if len(normalized) > maximum_length:
        raise ComputerUseArgumentsError(f"{field} is too long")
    return normalized


def _required_integer(
    value: Mapping[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ComputerUseArgumentsError(f"{field} must be an integer")
    if not minimum <= raw <= maximum:
        raise ComputerUseArgumentsError(f"{field} is outside the allowed range")
    return raw


def _optional_integer(
    value: Mapping[str, Any],
    field: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if field not in value:
        return default
    return _required_integer(
        value,
        field,
        minimum=minimum,
        maximum=maximum,
    )
