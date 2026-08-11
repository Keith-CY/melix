from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from jsonschema import exceptions as jsonschema_exceptions
from jsonschema import validators as jsonschema_validators

from worker.runtime.agentic_tools import (
    AgenticToolRuntimeError,
    DeterministicAgenticToolRuntime,
)
from worker.runtime.computer_use_adapter import ComputerUseToolAdapter
from worker.runtime.computer_use_client import ComputerUseBrokerClientError
from worker.runtime.mcp_client import (
    MCPCallCancelledError,
    MCPCallTimeoutError,
    MCPClientError,
    MCPClientMetricsSnapshot,
    MCPClientManager,
    MCPOperationMetricsSnapshot,
    MCPOwnerIdentity,
    MCPServerCapabilities,
    MCPSourceDefinition,
    MCPToolCatalog,
    MCPToolResult,
)
from worker.runtime.tool_observation import (
    ToolObservationPolicy,
    ToolObservationRecord,
    normalize_tool_observation,
)
from worker.runtime.tool_registry import (
    ToolDescriptor,
    agentic_tool_catalog_registry,
)
from worker.runtime.untrusted_context import untrusted_context_receipt


# The deterministic registry is broader than the live Agent execution context.
# Keep built-ins that require capabilities absent from this RPC out of both the
# advertised catalog and the live resolver. In particular, the current
# AgentToolExecutionContext has no operator-authorized workspace root or live
# skill/memory store. Advertising these fixture-backed adapters would promise
# execution context that this RPC cannot supply and would return misleading
# empty results for otherwise valid calls.
_LIVE_AGENT_UNAVAILABLE_BUILTINS = frozenset(
    {"workspace_file", "skill_lookup", "memory_lookup"}
)


class ToolExecutionRuntimeError(RuntimeError):
    code = "tool_execution_runtime_error"


class ToolAdmissionRequiredError(ToolExecutionRuntimeError):
    code = "tool_admission_required"


class ToolCallIdentityError(ToolExecutionRuntimeError):
    code = "tool_call_identity_invalid"


class ToolCallAlreadyExistsError(ToolExecutionRuntimeError):
    code = "tool_call_already_exists"


class ToolNotFoundError(ToolExecutionRuntimeError):
    code = "tool_not_found"


class ToolArgumentsSchemaError(ToolExecutionRuntimeError):
    code = "tool_arguments_schema_invalid"


class ToolCatalogSchemaError(ToolExecutionRuntimeError):
    code = "tool_catalog_schema_invalid"


class ToolOwnerScopeError(ToolExecutionRuntimeError):
    code = "tool_owner_scope_mismatch"


class ToolRunTerminalError(ToolExecutionRuntimeError):
    code = "tool_run_terminal"


class ToolTerminalRecordCapacityError(ToolExecutionRuntimeError):
    code = "tool_terminal_record_capacity_exhausted"


@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str
    session_id: str
    branch_id: str
    actor_id: str
    admission_state: str
    approval_grant_digest: str = ""
    policy_revision: str = ""
    deadline_unix_ms: int = 0
    control_plane_authorization_key_id: str = ""
    control_plane_authorization_algorithm: str = ""
    control_plane_authorization_payload: bytes = b""
    control_plane_authorization_signature: bytes = b""

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ToolCallIdentityError("run_id must not be blank")
        for field_name, value in (
            ("session_id", self.session_id),
            ("branch_id", self.branch_id),
            ("actor_id", self.actor_id),
        ):
            if not value.strip():
                raise ToolCallIdentityError(f"{field_name} must not be blank")
        if self.deadline_unix_ms < 0:
            raise ToolCallIdentityError("deadline_unix_ms must not be negative")

    @property
    def owner(self) -> MCPOwnerIdentity:
        return MCPOwnerIdentity(
            session_id=self.session_id,
            branch_id=self.branch_id,
            actor_id=self.actor_id,
        )


@dataclass(frozen=True)
class ToolExecutionCall:
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    source_id: str = ""
    expected_schema_digest: str = ""
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ToolCallIdentityError("call_id must not be blank")
        if not self.tool_name.strip():
            raise ToolCallIdentityError("tool_name must not be blank")
        if not isinstance(self.arguments, Mapping):
            raise ToolCallIdentityError("tool arguments must be a JSON object")
        try:
            encoded = json.dumps(
                dict(self.arguments),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            decoded = json.loads(encoded)
        except (TypeError, ValueError) as error:
            raise ToolCallIdentityError(
                "tool arguments must be JSON serializable"
            ) from error
        if not isinstance(decoded, dict):
            raise ToolCallIdentityError("tool arguments must be a JSON object")


@dataclass(frozen=True)
class ToolCatalogEntry:
    source_id: str
    adapter_kind: str
    name: str
    source_tool_name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    schema_digest: str
    risk_class: str
    replayability: str
    annotations_untrusted: bool


@dataclass(frozen=True)
class ToolCatalogReceipt:
    schema_version: str
    tools: tuple[ToolCatalogEntry, ...]
    catalog_digest: str
    source_count: int
    live_source_count: int


@dataclass(frozen=True)
class ToolExecutionResult:
    run_id: str
    call_id: str
    tool_name: str
    source_id: str
    adapter_kind: str
    status: str
    observation: ToolObservationRecord
    duration_ms: float
    receipt: Mapping[str, Any]
    evidence_reference: str = ""


@dataclass(frozen=True)
class ToolCancellationReceipt:
    run_id: str
    call_id: str
    disposition: str
    adapter_kind: str
    source_id: str
    cancellation_id: str
    side_effect_state: str = "unknown"

    @property
    def side_effect_committed(self) -> bool:
        """Deprecated compatibility projection for the v1 boolean field."""

        return self.side_effect_state == "committed"


@dataclass(frozen=True)
class ToolRunCancellationReceipt:
    run_id: str
    cancellation_id: str
    disposition: str
    side_effect_state: str
    calls: tuple[ToolCancellationReceipt, ...] = ()
    computer_use_disposition: str = "not_found"


@dataclass(frozen=True)
class ToolExecutionRuntimeMetricsSnapshot:
    schema_version: str
    mcp: MCPClientMetricsSnapshot
    worker_to_adapter_cancel: MCPOperationMetricsSnapshot


@dataclass
class _MutableToolOperationMetrics:
    invocation_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    maximum_latency_ms: float = 0.0

    def record(self, latency_ms: float, *, failed: bool) -> None:
        bounded_latency_ms = max(0.0, latency_ms)
        self.invocation_count += 1
        self.failure_count += int(failed)
        self.total_latency_ms += bounded_latency_ms
        self.last_latency_ms = bounded_latency_ms
        self.maximum_latency_ms = max(
            self.maximum_latency_ms,
            bounded_latency_ms,
        )

    def snapshot(self) -> MCPOperationMetricsSnapshot:
        return MCPOperationMetricsSnapshot(
            invocation_count=self.invocation_count,
            failure_count=self.failure_count,
            total_latency_ms=self.total_latency_ms,
            last_latency_ms=self.last_latency_ms,
            maximum_latency_ms=self.maximum_latency_ms,
        )


@dataclass
class _ActiveExecution:
    owner: MCPOwnerIdentity
    adapter_kind: str
    source_id: str
    task: asyncio.Task[ToolExecutionResult]


@dataclass(frozen=True)
class _TerminalExecution:
    owner: MCPOwnerIdentity
    receipt: ToolCancellationReceipt


@dataclass(frozen=True)
class _CompletedExecution:
    owner: MCPOwnerIdentity
    execution_digest: str
    result: ToolExecutionResult


@dataclass(frozen=True)
class _CallCancellation:
    owner: MCPOwnerIdentity
    task: asyncio.Task[ToolCancellationReceipt]


@dataclass(frozen=True)
class _RunCancellation:
    owner: MCPOwnerIdentity
    task: asyncio.Task[ToolRunCancellationReceipt]


_EVIDENCE_SCHEMA_VERSION = "melix.agent_tool_execution_evidence.v1"
_EVIDENCE_RELATIVE_ROOT = Path("state") / "agent-tool-evidence"
_EVIDENCE_MAX_BYTES = 262_144
_EVIDENCE_MAX_DEPTH = 12
_EVIDENCE_MAX_ITEMS = 256
_EVIDENCE_MAX_TEXT_BYTES = 16_384
_MAX_TOOL_SCHEMA_BYTES = 65_536
_MAX_TOOL_SCHEMA_DEPTH = 32
_MAX_TOOL_SCHEMA_NODES = 4_096
# Terminal identities remain authoritative for this explicit retry horizon.
# Capacity exhaustion rejects new identities; unexpired records are never
# evicted to make room because doing so could replay a side effect.
_DEFAULT_MAXIMUM_TERMINAL_RECORDS = 4_096
_DEFAULT_TERMINAL_RECORD_RETENTION_SECONDS = 3_600.0
_SENSITIVE_EVIDENCE_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|private[_-]?key|"
    r"secret|signature|token|api[_-]?key|raw[_-]?prompt|arguments?)",
    re.IGNORECASE,
)
_BEARER_CREDENTIAL = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")


class ToolExecutionEvidenceStore:
    """Persist one bounded, sanitized execution envelope under MELIX_HOME."""

    def __init__(
        self,
        melix_home: str | Path,
        *,
        max_bytes: int = _EVIDENCE_MAX_BYTES,
    ) -> None:
        if max_bytes < 4_096:
            raise ValueError("tool evidence max_bytes must be at least 4096")
        self._melix_home = Path(melix_home).expanduser().resolve()
        if self._melix_home == Path(self._melix_home.anchor):
            raise ValueError("tool evidence MELIX_HOME must not be a filesystem root")
        self._root = (self._melix_home / _EVIDENCE_RELATIVE_ROOT).resolve()
        if not self._root.is_relative_to(self._melix_home):
            raise ValueError("tool evidence root escaped MELIX_HOME")
        self._max_bytes = max_bytes

    def persist(self, result: ToolExecutionResult) -> str:
        run_component = _identity_digest(result.run_id)
        call_component = _identity_digest(result.call_id)
        target = self._root / run_component / f"{call_component}.json"
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(self._root):
            raise ValueError("tool evidence target escaped its bounded root")
        os.chmod(self._root, 0o700)
        os.chmod(resolved_target.parent, 0o700)

        reference = resolved_target.relative_to(self._melix_home).as_posix()
        execution_receipt = dict(result.receipt)
        execution_receipt["evidence_reference"] = reference
        execution_receipt["evidence_persisted"] = True
        payload = {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "run_id_digest": run_component,
            "call_id_digest": call_component,
            "tool_name": result.tool_name,
            "source_id": result.source_id,
            "adapter_kind": result.adapter_kind,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "observation": result.observation.as_agentic_trace_observation(),
            "execution_receipt": execution_receipt,
            "persisted_at_unix_ms": int(time.time() * 1_000),
        }
        sanitized = _sanitize_evidence_value(payload)
        encoded = _canonical_json_bytes(sanitized)
        if len(encoded) > self._max_bytes:
            sanitized = {
                "schema_version": _EVIDENCE_SCHEMA_VERSION,
                "run_id_digest": run_component,
                "call_id_digest": call_component,
                "tool_name": _bounded_evidence_text(result.tool_name),
                "source_id": _bounded_evidence_text(result.source_id),
                "adapter_kind": result.adapter_kind,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "observation_replay": result.observation.replay.as_dict(),
                "observation_metrics": result.observation.metrics.as_dict(),
                "payload_omitted": True,
                "original_sanitized_bytes": len(encoded),
                "persisted_at_unix_ms": int(time.time() * 1_000),
            }
            encoded = _canonical_json_bytes(sanitized)
        if len(encoded) > self._max_bytes:
            raise ValueError("bounded tool evidence envelope exceeded max_bytes")

        descriptor, temporary_path = tempfile.mkstemp(
            dir=resolved_target.parent,
            prefix=f".{resolved_target.name}.",
            suffix=".tmp",
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, resolved_target)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary_path)
        return reference


class ToolExecutionRuntime:
    """Deep worker-owned seam for deterministic and live tool execution."""

    def __init__(
        self,
        *,
        deterministic_runtime: DeterministicAgenticToolRuntime | None = None,
        mcp_manager: MCPClientManager | None = None,
        computer_use_adapter: ComputerUseToolAdapter | None = None,
        observation_policy: ToolObservationPolicy | None = None,
        evidence_store: ToolExecutionEvidenceStore | None = None,
        latency_clock: Callable[[], float] = time.perf_counter,
        maximum_terminal_records: int = _DEFAULT_MAXIMUM_TERMINAL_RECORDS,
        terminal_record_retention_seconds: float = (
            _DEFAULT_TERMINAL_RECORD_RETENTION_SECONDS
        ),
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_terminal_records < 1:
            raise ValueError("maximum_terminal_records must be positive")
        if (
            not math.isfinite(terminal_record_retention_seconds)
            or terminal_record_retention_seconds <= 0
        ):
            raise ValueError(
                "terminal_record_retention_seconds must be finite and positive"
            )
        self._registry = agentic_tool_catalog_registry()
        self._builtin_by_name = {
            tool.name: tool
            for tool in self._registry.tools
            if tool.name not in _LIVE_AGENT_UNAVAILABLE_BUILTINS
        }
        self._deterministic_runtime = (
            deterministic_runtime or DeterministicAgenticToolRuntime()
        )
        self._mcp_manager = mcp_manager or MCPClientManager()
        self._computer_use_adapter = computer_use_adapter
        self._observation_policy = observation_policy or ToolObservationPolicy()
        self._evidence_store = evidence_store
        self._latency_clock = latency_clock
        self._maximum_terminal_records = maximum_terminal_records
        self._terminal_record_retention_seconds = (
            terminal_record_retention_seconds
        )
        self._monotonic_clock = monotonic_clock
        self._worker_to_adapter_cancel_metrics = _MutableToolOperationMetrics()
        self._metrics_lock = threading.Lock()
        self._mcp_capabilities: dict[str, MCPServerCapabilities] = {}
        self._mcp_catalogs: dict[str, MCPToolCatalog] = {}
        self._mcp_owner_source_ids: dict[
            tuple[str, str, str],
            set[str],
        ] = {}
        self._active: dict[tuple[str, str], _ActiveExecution] = {}
        self._terminal: dict[tuple[str, str], _TerminalExecution] = {}
        self._completed: dict[tuple[str, str], _CompletedExecution] = {}
        self._call_terminal_expires_at: dict[tuple[str, str], float] = {}
        self._call_cancellations: dict[
            tuple[str, str], _CallCancellation
        ] = {}
        self._run_owners: dict[str, MCPOwnerIdentity] = {}
        self._run_owner_expires_at: dict[str, float] = {}
        self._run_cancellations: dict[str, _RunCancellation] = {}
        self._run_record_expires_at: dict[str, float] = {}
        self._schema_validators: dict[tuple[str, bool], Any] = {}
        self._lock = asyncio.Lock()

    async def initialize_mcp_source(
        self,
        source: MCPSourceDefinition,
        owner: MCPOwnerIdentity,
        *,
        lease_ttl_seconds: float = 300.0,
    ) -> MCPServerCapabilities:
        try:
            capabilities = await self._mcp_manager.initialize(
                source,
                owner,
                lease_ttl_seconds=lease_ttl_seconds,
            )
            catalog = await self._mcp_manager.list_tools(
                source.source_id,
                owner,
            )
        except BaseException:
            raise
        self._mcp_capabilities[source.source_id] = capabilities
        self._mcp_catalogs[source.source_id] = catalog
        self._mcp_owner_source_ids.setdefault(owner.key, set()).add(
            source.source_id
        )
        return capabilities

    async def remove_mcp_source(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
    ) -> None:
        await self._mcp_manager.release(source_id, owner)
        owner_sources = self._mcp_owner_source_ids.get(owner.key)
        if owner_sources is not None:
            owner_sources.discard(source_id)
            if not owner_sources:
                self._mcp_owner_source_ids.pop(owner.key, None)
        if not any(
            source_id in source_ids
            for source_ids in self._mcp_owner_source_ids.values()
        ):
            self._mcp_capabilities.pop(source_id, None)
            self._mcp_catalogs.pop(source_id, None)

    async def release_mcp_owner(self, owner: MCPOwnerIdentity) -> None:
        source_ids = set(self._mcp_owner_source_ids.pop(owner.key, set()))
        await self._mcp_manager.release_owner(owner)
        for source_id in source_ids:
            if not any(
                source_id in retained
                for retained in self._mcp_owner_source_ids.values()
            ):
                self._mcp_capabilities.pop(source_id, None)
                self._mcp_catalogs.pop(source_id, None)

    async def list_tools(
        self,
        *,
        owner: MCPOwnerIdentity | None = None,
        refresh_mcp_catalogs: bool = False,
        mcp_source_ids: set[str] | frozenset[str] | None = None,
    ) -> ToolCatalogReceipt:
        owner_source_ids = (
            set()
            if owner is None
            else set(self._mcp_owner_source_ids.get(owner.key, set()))
        )
        selected_source_ids = (
            owner_source_ids
            if mcp_source_ids is None
            else set(mcp_source_ids)
        )
        if selected_source_ids and owner is None:
            raise ToolOwnerScopeError(
                "live MCP tool catalogs require an exact owner"
            )
        if not selected_source_ids.issubset(owner_source_ids):
            raise ToolOwnerScopeError(
                "MCP tool catalog source is not leased to this owner"
            )
        selected_source_ids.intersection_update(self._mcp_catalogs)
        for source_id in sorted(selected_source_ids):
            assert owner is not None
            self._mcp_catalogs[source_id] = await self._mcp_manager.list_tools(
                source_id,
                owner,
                refresh=refresh_mcp_catalogs,
            )

        entries = [
            _builtin_catalog_entry(descriptor)
            for descriptor in self._builtin_by_name.values()
        ]
        for source_id in sorted(selected_source_ids):
            catalog = self._mcp_catalogs[source_id]
            entries.extend(
                ToolCatalogEntry(
                    source_id=source_id,
                    adapter_kind="mcp",
                    name=tool.canonical_name,
                    source_tool_name=tool.name,
                    # MCP titles, descriptions, and annotations are untrusted
                    # server data. Keep those values out of the trusted effect
                    # summary consumed by approval UI and policy.
                    title=tool.canonical_name,
                    description=(
                        "Configured MCP tool. Server-provided descriptions "
                        "and annotations are untrusted; inspect the exact "
                        "arguments and apply operator policy before execution."
                    ),
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                    schema_digest=tool.schema_digest,
                    risk_class="unknown",
                    replayability="evidence_only",
                    annotations_untrusted=True,
                )
                for tool in catalog.tools
            )
        computer_available = False
        if self._computer_use_adapter is not None:
            try:
                await self._computer_use_adapter.initialize()
                computer_available = True
            except ComputerUseBrokerClientError:
                computer_available = False
        if computer_available and self._computer_use_adapter is not None:
            tool = self._computer_use_adapter.definition
            entries.append(
                ToolCatalogEntry(
                    source_id=tool.source_id,
                    adapter_kind=tool.adapter_kind,
                    name=tool.name,
                    source_tool_name=tool.name,
                    title=tool.title,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    output_schema=None,
                    schema_digest=tool.schema_digest,
                    risk_class=tool.risk_class,
                    replayability=tool.replayability,
                    annotations_untrusted=tool.annotations_untrusted,
                )
            )
        entries.sort(key=lambda entry: (entry.source_id, entry.name))
        digest = _digest_json(
            [
                {
                    "source_id": entry.source_id,
                    "name": entry.name,
                    "schema_digest": entry.schema_digest,
                    "adapter_kind": entry.adapter_kind,
                }
                for entry in entries
            ]
        )
        return ToolCatalogReceipt(
            schema_version="melix.tool_execution_catalog.v1",
            tools=tuple(entries),
            catalog_digest=digest,
            source_count=(
                1
                + len(selected_source_ids)
                + int(self._computer_use_adapter is not None)
            ),
            live_source_count=(
                len(selected_source_ids)
                + int(computer_available)
            ),
        )

    async def execute(
        self,
        call: ToolExecutionCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        _validate_admission(context)
        _validate_deadline(context)
        owner = context.owner
        adapter_kind, source_id = self._resolve_adapter(call, owner=owner)
        self._validate_call_schema(
            call,
            adapter_kind=adapter_kind,
            source_id=source_id,
        )
        key = (context.run_id, call.call_id)
        execution_digest = _execution_digest(call, context)
        task = asyncio.current_task()
        if task is None:
            raise ToolExecutionRuntimeError(
                "tool execution requires an active asyncio task"
            )

        async with self._lock:
            now = self._monotonic_clock()
            self._prune_terminal_records_locked(now)
            run_owner = self._run_owners.get(context.run_id)
            if run_owner is not None and run_owner != owner:
                raise ToolOwnerScopeError(
                    "agent run identity belongs to another owner"
                )
            if context.run_id in self._run_cancellations:
                raise ToolRunTerminalError(
                    "agent run no longer accepts tool execution"
                )
            cached = self._completed.get(key)
            if cached is not None:
                if cached.owner != owner:
                    raise ToolOwnerScopeError(
                        "tool call cache belongs to another owner"
                    )
                if cached.execution_digest != execution_digest:
                    raise ToolCallAlreadyExistsError(
                        f"tool call {call.call_id!r} was replayed with changed inputs"
                    )
                return cached.result
            active = self._active.get(key)
            terminal = self._terminal.get(key)
            existing_owner = (
                active.owner
                if active is not None
                else terminal.owner if terminal is not None else None
            )
            if existing_owner is not None and existing_owner != owner:
                raise ToolOwnerScopeError(
                    "tool call identity belongs to another owner"
                )
            if active is not None or terminal is not None:
                raise ToolCallAlreadyExistsError(
                    f"tool call {call.call_id!r} already exists in run"
                )
            retained_call_keys = set(self._active).union(
                self._call_terminal_expires_at
            )
            if (
                key not in retained_call_keys
                and len(retained_call_keys) >= self._maximum_terminal_records
            ):
                raise ToolTerminalRecordCapacityError(
                    "tool call terminal-record capacity is exhausted until "
                    "the configured retry horizon elapses"
                )
            if (
                run_owner is None
                and len(self._run_owners) >= self._maximum_terminal_records
            ):
                raise ToolTerminalRecordCapacityError(
                    "tool run identity capacity is exhausted until the "
                    "configured retry horizon elapses"
                )
            self._run_owners[context.run_id] = owner
            self._run_owner_expires_at[context.run_id] = (
                now + self._terminal_record_retention_seconds
            )
            active_execution = _ActiveExecution(
                owner=owner,
                adapter_kind=adapter_kind,
                source_id=source_id,
                task=task,
            )
            self._active[key] = active_execution

        result: ToolExecutionResult | None = None
        try:
            if adapter_kind == "builtin":
                result = await self._execute_builtin(call, context)
            elif adapter_kind == "computer":
                result = await self._execute_computer(call, context)
            else:
                result = await self._execute_mcp(call, context, source_id)
        except asyncio.CancelledError:
            cancellation_side_effect_state = (
                "none" if adapter_kind == "builtin" else "unknown"
            )
            cancellation_task: asyncio.Task[ToolCancellationReceipt] | None = None
            async with self._lock:
                terminal_execution = self._terminal.get(key)
                accepted_cancellation = (
                    terminal_execution.receipt
                    if terminal_execution is not None
                    and terminal_execution.owner == owner
                    else None
                )
                if (
                    accepted_cancellation is None
                    and adapter_kind in {"mcp", "computer"}
                ):
                    cancellation = self._call_cancellations.get(key)
                    if cancellation is None:
                        cancellation_task = asyncio.create_task(
                            self._cancel_active_execution(
                                key,
                                active_execution,
                                owner,
                                _stable_cancellation_id(
                                    owner,
                                    context.run_id,
                                    call.call_id,
                                ),
                                cancel_local_task_on_accept=False,
                            ),
                            name=(
                                "melix-cleanup-cancelled-agent-tool-"
                                f"{_identity_digest(context.run_id)}-"
                                f"{_identity_digest(call.call_id)}"
                            ),
                        )
                        self._call_cancellations[key] = _CallCancellation(
                            owner=owner,
                            task=cancellation_task,
                        )
                    elif cancellation.owner == owner:
                        cancellation_task = cancellation.task
            if (
                accepted_cancellation is not None
                and accepted_cancellation.disposition == "accepted"
            ):
                # The cancellation RPC already captured the adapter's closest
                # commit-point evidence. Re-querying after task cancellation
                # can only downgrade a truthful `none`/`committed` receipt to
                # `unknown` once the adapter has moved the call to terminal.
                cancellation_side_effect_state = (
                    accepted_cancellation.side_effect_state
                )
            elif cancellation_task is not None:
                cancellation = await asyncio.shield(cancellation_task)
                cancellation_side_effect_state = (
                    cancellation.side_effect_state
                )
            result = self._cancelled_result(
                call,
                context,
                source_id=source_id,
                adapter_kind=adapter_kind,
                side_effect_state=cancellation_side_effect_state,
            )
        finally:
            if result is not None:
                persistence_task = asyncio.create_task(
                    asyncio.to_thread(
                        self._persist_execution_evidence,
                        result,
                    )
                )
                try:
                    result = await asyncio.shield(persistence_task)
                except asyncio.CancelledError:
                    # Tool cancellation is represented by the typed terminal
                    # result/receipt. Do not let the task-level wake-up tear
                    # down the evidence commit that makes that result durable.
                    current_task = asyncio.current_task()
                    if current_task is not None:
                        while current_task.cancelling():
                            current_task.uncancel()
                    result = await persistence_task
            async with self._lock:
                self._active.pop(key, None)
                terminal_expires_at = (
                    self._monotonic_clock()
                    + self._terminal_record_retention_seconds
                )
                if result is not None:
                    self._completed[key] = _CompletedExecution(
                        owner=owner,
                        execution_digest=execution_digest,
                        result=result,
                    )
                if key not in self._terminal:
                    self._terminal[key] = _TerminalExecution(
                        owner=owner,
                        receipt=ToolCancellationReceipt(
                            run_id=context.run_id,
                            call_id=call.call_id,
                            disposition="already_terminal",
                            adapter_kind=adapter_kind,
                            source_id=source_id,
                            cancellation_id=_stable_cancellation_id(
                                owner,
                                context.run_id,
                                call.call_id,
                            ),
                            side_effect_state=(
                                "none"
                                if adapter_kind == "builtin"
                                else "unknown"
                            ),
                        ),
                    )
                self._call_terminal_expires_at[key] = terminal_expires_at
                self._run_owner_expires_at[context.run_id] = (
                    terminal_expires_at
                )
        assert result is not None
        return result

    async def cancel(
        self,
        run_id: str,
        call_id: str,
        owner: MCPOwnerIdentity,
        cancellation_id: str = "",
    ) -> ToolCancellationReceipt:
        key = (run_id, call_id)
        # Caller-generated IDs may change across UI retries. The worker owns a
        # deterministic terminal identity so every repeat returns one receipt.
        del cancellation_id
        stable_cancellation_id = _stable_cancellation_id(
            owner,
            run_id,
            call_id,
        )
        async with self._lock:
            self._prune_terminal_records_locked(self._monotonic_clock())
            active = self._active.get(key)
            terminal = self._terminal.get(key)
            cancellation = self._call_cancellations.get(key)
            if terminal is not None:
                if terminal.owner != owner:
                    return ToolCancellationReceipt(
                        run_id=run_id,
                        call_id=call_id,
                        disposition="scope_mismatch",
                        adapter_kind="",
                        source_id="",
                        cancellation_id=stable_cancellation_id,
                        side_effect_state="unknown",
                    )
                return ToolCancellationReceipt(
                    run_id=run_id,
                    call_id=call_id,
                    disposition="already_terminal",
                    adapter_kind=terminal.receipt.adapter_kind,
                    source_id=terminal.receipt.source_id,
                    cancellation_id=terminal.receipt.cancellation_id,
                    side_effect_state=terminal.receipt.side_effect_state,
                )
            if active is None:
                return ToolCancellationReceipt(
                    run_id=run_id,
                    call_id=call_id,
                    disposition="not_found",
                    adapter_kind="",
                    source_id="",
                    cancellation_id=stable_cancellation_id,
                    side_effect_state="unknown",
                )
            if active.owner != owner:
                return ToolCancellationReceipt(
                    run_id=run_id,
                    call_id=call_id,
                    disposition="scope_mismatch",
                    adapter_kind="",
                    source_id="",
                    cancellation_id=stable_cancellation_id,
                    side_effect_state="unknown",
                )
            if cancellation is not None:
                if cancellation.owner != owner:
                    return ToolCancellationReceipt(
                        run_id=run_id,
                        call_id=call_id,
                        disposition="scope_mismatch",
                        adapter_kind="",
                        source_id="",
                        cancellation_id=stable_cancellation_id,
                        side_effect_state="unknown",
                    )
                cancellation_task = cancellation.task
            else:
                cancellation_task = asyncio.create_task(
                    self._cancel_active_execution(
                        key,
                        active,
                        owner,
                        stable_cancellation_id,
                        cancel_local_task_on_accept=True,
                    ),
                    name=(
                        "melix-cancel-agent-tool-"
                        f"{_identity_digest(run_id)}-"
                        f"{_identity_digest(call_id)}"
                    ),
                )
                self._call_cancellations[key] = _CallCancellation(
                    owner=owner,
                    task=cancellation_task,
                )

        # Cancellation remains owned by the runtime once admitted. An RPC
        # waiter disconnecting must not cancel the shared adapter flight and
        # let another cleanup path dispatch the same cancellation again.
        return await asyncio.shield(cancellation_task)

    async def _cancel_active_execution(
        self,
        key: tuple[str, str],
        active: _ActiveExecution,
        owner: MCPOwnerIdentity,
        stable_cancellation_id: str,
        *,
        cancel_local_task_on_accept: bool,
    ) -> ToolCancellationReceipt:
        run_id, call_id = key
        cancel_local_task = False
        if active.adapter_kind == "mcp":
            try:
                mcp_receipt = await self._measure_worker_to_adapter_cancel(
                    self._mcp_manager.cancel(
                        active.source_id,
                        owner,
                        run_id,
                        call_id,
                    )
                )
            except MCPClientError:
                # The exact runtime owner was already verified above. If its
                # source lease expired or the transport disappeared while the
                # call remained active, local task cancellation is still the
                # only truthful bounded action; MCP side effects are unknown.
                disposition = "accepted"
                side_effect_state = "unknown"
                cancel_local_task = True
            else:
                disposition = (
                    "accepted"
                    if mcp_receipt.disposition in {"accepted", "not_found"}
                    else mcp_receipt.disposition
                )
                side_effect_state = (
                    "unknown"
                    if mcp_receipt.disposition == "not_found"
                    else mcp_receipt.side_effect_state
                )
                cancel_local_task = mcp_receipt.disposition in {
                    "accepted",
                    "not_found",
                }
        elif (
            active.adapter_kind == "computer"
            and self._computer_use_adapter is not None
        ):
            try:
                computer_receipt = (
                    await self._measure_worker_to_adapter_cancel(
                        self._computer_use_adapter.cancel(
                            run_id,
                            call_id,
                        )
                    )
                )
            except ComputerUseBrokerClientError:
                # The broker cancellation path failed after this exact owner
                # and active call were verified. Cancel the local RPC task as
                # the bounded fallback, but retain unknown side-effect truth.
                disposition = "accepted"
                side_effect_state = "unknown"
                cancel_local_task = True
            else:
                disposition = computer_receipt.disposition
                side_effect_state = (
                    "committed"
                    if computer_receipt.side_effect_committed
                    else (
                        "none"
                        if computer_receipt.disposition == "accepted"
                        else "unknown"
                    )
                )
                cancel_local_task = disposition == "accepted"
        else:
            # Deterministic built-ins are synchronous and have no side-effecting
            # live adapter. Once dispatched they cannot truthfully acknowledge
            # cooperative cancellation.
            disposition = "too_late"
            side_effect_state = "none"

        receipt = ToolCancellationReceipt(
            run_id=run_id,
            call_id=call_id,
            disposition=disposition,
            adapter_kind=active.adapter_kind,
            source_id=active.source_id,
            cancellation_id=stable_cancellation_id,
            side_effect_state=side_effect_state,
        )
        if disposition == "accepted":
            async with self._lock:
                current_active = self._active.get(key)
                if current_active is not active:
                    terminal = self._terminal.get(key)
                    if terminal is not None and terminal.owner == owner:
                        return ToolCancellationReceipt(
                            run_id=run_id,
                            call_id=call_id,
                            disposition="already_terminal",
                            adapter_kind=terminal.receipt.adapter_kind,
                            source_id=terminal.receipt.source_id,
                            cancellation_id=terminal.receipt.cancellation_id,
                            side_effect_state=(
                                terminal.receipt.side_effect_state
                            ),
                        )
                self._terminal[key] = _TerminalExecution(
                    owner=owner,
                    receipt=receipt,
                )
                self._call_terminal_expires_at[key] = (
                    self._monotonic_clock()
                    + self._terminal_record_retention_seconds
                )
            # Publish the accepted terminal receipt before waking the
            # execution task. Its CancelledError handler can then reuse the
            # exact adapter result instead of dispatching a second cancel.
            if cancel_local_task and cancel_local_task_on_accept:
                active.task.cancel()
        return receipt

    async def cancel_run(
        self,
        run_id: str,
        owner: MCPOwnerIdentity,
        cancellation_id: str = "",
    ) -> ToolRunCancellationReceipt:
        if not run_id.strip():
            raise ToolCallIdentityError("run_id must not be blank")
        del cancellation_id
        stable_cancellation_id = _stable_run_cancellation_id(owner, run_id)
        joined_existing = False
        async with self._lock:
            now = self._monotonic_clock()
            self._prune_terminal_records_locked(now)
            existing_owner = self._run_owners.get(run_id)
            if existing_owner is not None and existing_owner != owner:
                return ToolRunCancellationReceipt(
                    run_id=run_id,
                    cancellation_id=stable_cancellation_id,
                    disposition="scope_mismatch",
                    side_effect_state="unknown",
                )
            existing = self._run_cancellations.get(run_id)
            if existing is not None:
                if existing.owner != owner:
                    return ToolRunCancellationReceipt(
                        run_id=run_id,
                        cancellation_id=stable_cancellation_id,
                        disposition="scope_mismatch",
                        side_effect_state="unknown",
                    )
                task = existing.task
                joined_existing = True
            else:
                if (
                    existing_owner is None
                    and len(self._run_owners)
                    >= self._maximum_terminal_records
                ):
                    raise ToolTerminalRecordCapacityError(
                        "tool run cancellation capacity is exhausted until "
                        "the configured retry horizon elapses"
                    )
                self._run_owners[run_id] = owner
                self._run_owner_expires_at[run_id] = (
                    now + self._terminal_record_retention_seconds
                )
                self._run_record_expires_at[run_id] = (
                    now + self._terminal_record_retention_seconds
                )
                task = asyncio.create_task(
                    self._cancel_run_resources_and_finalize(
                        run_id,
                        owner,
                        stable_cancellation_id,
                    ),
                    name=f"melix-cancel-agent-run-{_identity_digest(run_id)}",
                )
                self._run_cancellations[run_id] = _RunCancellation(
                    owner=owner,
                    task=task,
                )

        receipt = await asyncio.shield(task)
        if joined_existing and task.done():
            return replace(receipt, disposition="already_terminal")
        await self._trim_terminal_run_cancellations()
        return receipt

    async def _cancel_run_resources_and_finalize(
        self,
        run_id: str,
        owner: MCPOwnerIdentity,
        cancellation_id: str,
    ) -> ToolRunCancellationReceipt:
        try:
            return await self._cancel_run_resources(
                run_id,
                owner,
                cancellation_id,
            )
        finally:
            # The retry horizon begins when cleanup becomes terminal, not when
            # cancellation was admitted. Keep this in the owned task so the
            # tombstone is finalized even if the first RPC waiter disconnects.
            async with self._lock:
                terminal_expires_at = (
                    self._monotonic_clock()
                    + self._terminal_record_retention_seconds
                )
                self._run_record_expires_at[run_id] = terminal_expires_at
                self._run_owner_expires_at[run_id] = terminal_expires_at

    async def _cancel_run_resources(
        self,
        run_id: str,
        owner: MCPOwnerIdentity,
        cancellation_id: str,
    ) -> ToolRunCancellationReceipt:
        async with self._lock:
            active_calls = [
                (call_id, active)
                for (candidate_run_id, call_id), active in self._active.items()
                if candidate_run_id == run_id and active.owner == owner
            ]

        call_receipts = await asyncio.gather(
            *(
                self.cancel(run_id, call_id, owner, cancellation_id)
                for call_id, _ in active_calls
            )
        )
        computer_disposition = "not_found"
        computer_side_effect_state = "none"
        if self._computer_use_adapter is not None:
            try:
                computer_receipt = await self._measure_worker_to_adapter_cancel(
                    self._computer_use_adapter.cancel(
                        run_id,
                        f"__run_cleanup__:{cancellation_id}",
                    )
                )
            except ComputerUseBrokerClientError:
                computer_disposition = "too_late"
                computer_side_effect_state = "unknown"
            else:
                computer_disposition = computer_receipt.disposition
                computer_side_effect_state = (
                    "committed"
                    if computer_receipt.side_effect_committed
                    else (
                        "none"
                        if computer_receipt.disposition
                        in {"accepted", "already_terminal", "not_found"}
                        else "unknown"
                    )
                )

        side_effect_state = _combined_side_effect_state(
            [
                *(receipt.side_effect_state for receipt in call_receipts),
                computer_side_effect_state,
            ]
        )
        disposition = (
            "too_late"
            if any(
                receipt.disposition in {"too_late", "scope_mismatch"}
                for receipt in call_receipts
            )
            or computer_disposition in {"too_late", "scope_mismatch"}
            else "accepted"
        )
        return ToolRunCancellationReceipt(
            run_id=run_id,
            cancellation_id=cancellation_id,
            disposition=disposition,
            side_effect_state=side_effect_state,
            calls=tuple(call_receipts),
            computer_use_disposition=computer_disposition,
        )

    def metrics_snapshot(self) -> ToolExecutionRuntimeMetricsSnapshot:
        mcp_snapshot = self._mcp_manager.metrics_snapshot()
        with self._metrics_lock:
            worker_to_adapter_cancel = (
                self._worker_to_adapter_cancel_metrics.snapshot()
            )
        return ToolExecutionRuntimeMetricsSnapshot(
            schema_version="melix.tool_execution_runtime_metrics.v1",
            mcp=mcp_snapshot,
            worker_to_adapter_cancel=worker_to_adapter_cancel,
        )

    async def _measure_worker_to_adapter_cancel(
        self,
        operation: Awaitable[Any],
    ) -> Any:
        started = self._latency_clock()
        failed = True
        try:
            result = await operation
            failed = False
            return result
        finally:
            with self._metrics_lock:
                self._worker_to_adapter_cancel_metrics.record(
                    (self._latency_clock() - started) * 1_000,
                    failed=failed,
                )

    async def _trim_terminal_run_cancellations(self) -> None:
        async with self._lock:
            self._prune_terminal_records_locked(self._monotonic_clock())

    def _prune_terminal_records_locked(self, now: float) -> None:
        expired_calls = [
            key
            for key, expires_at in self._call_terminal_expires_at.items()
            if expires_at <= now
            and key not in self._active
            and (
                (cancellation := self._call_cancellations.get(key)) is None
                or cancellation.task.done()
            )
        ]
        for key in expired_calls:
            self._call_terminal_expires_at.pop(key, None)
            self._terminal.pop(key, None)
            self._completed.pop(key, None)
            self._call_cancellations.pop(key, None)

        expired_runs = [
            run_id
            for run_id, expires_at in self._run_record_expires_at.items()
            if expires_at <= now
            and (
                (cancellation := self._run_cancellations.get(run_id))
                is None
                or cancellation.task.done()
            )
        ]
        for run_id in expired_runs:
            self._run_record_expires_at.pop(run_id, None)
            self._run_cancellations.pop(run_id, None)

        for run_id, expires_at in list(self._run_owner_expires_at.items()):
            if expires_at > now or run_id in self._run_cancellations:
                continue
            has_active_call = any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._active
            )
            has_retained_call = any(
                candidate_run_id == run_id
                for candidate_run_id, _ in self._call_terminal_expires_at
            )
            if has_active_call or has_retained_call:
                continue
            self._run_owner_expires_at.pop(run_id, None)
            self._run_owners.pop(run_id, None)

    def _validate_call_schema(
        self,
        call: ToolExecutionCall,
        *,
        adapter_kind: str,
        source_id: str,
    ) -> None:
        schema, schema_digest = self._schema_for_call(
            call,
            adapter_kind=adapter_kind,
            source_id=source_id,
        )
        if call.expected_schema_digest and (
            call.expected_schema_digest != schema_digest
        ):
            raise ToolCatalogSchemaError(
                "tool schema digest changed before worker execution"
            )
        allow_regex_keywords = adapter_kind != "mcp"
        validator_cache_key = (schema_digest, allow_regex_keywords)
        validator = self._schema_validators.get(validator_cache_key)
        if validator is None:
            try:
                _assert_bounded_json_schema(
                    schema,
                    allow_regex_keywords=allow_regex_keywords,
                )
                validator_class = jsonschema_validators.validator_for(schema)
                validator_class.check_schema(schema)
                validator = validator_class(schema)
            except (
                ToolCatalogSchemaError,
                jsonschema_exceptions.SchemaError,
            ) as error:
                raise ToolCatalogSchemaError(
                    "tool catalog contains an invalid JSON schema"
                ) from error
            self._schema_validators[validator_cache_key] = validator
        try:
            errors = sorted(
                validator.iter_errors(dict(call.arguments)),
                key=lambda item: tuple(
                    str(component) for component in item.path
                ),
            )
        except Exception as error:
            raise ToolCatalogSchemaError(
                "tool catalog schema could not be evaluated safely"
            ) from error
        if errors:
            error = errors[0]
            path = "$"
            if error.path:
                path += "." + ".".join(
                    str(component)[:64] for component in error.path
                )
            raise ToolArgumentsSchemaError(
                "tool arguments failed JSON-schema admission at "
                f"{path} ({error.validator})"
            )

    def _schema_for_call(
        self,
        call: ToolExecutionCall,
        *,
        adapter_kind: str,
        source_id: str,
    ) -> tuple[Mapping[str, Any], str]:
        if adapter_kind == "builtin":
            descriptor = self._builtin_by_name[call.tool_name]
            return descriptor.schema_payload(), _builtin_schema_digest(descriptor)
        if adapter_kind == "computer":
            assert self._computer_use_adapter is not None
            definition = self._computer_use_adapter.definition
            return definition.input_schema, definition.schema_digest
        matches = [
            tool
            for tool in self._mcp_catalogs[source_id].tools
            if call.tool_name in {tool.name, tool.canonical_name}
        ]
        if len(matches) != 1:
            raise ToolNotFoundError(
                f"tool {call.tool_name!r} did not resolve to one live schema"
            )
        return matches[0].input_schema, matches[0].schema_digest

    def _persist_execution_evidence(
        self,
        result: ToolExecutionResult,
    ) -> ToolExecutionResult:
        if self._evidence_store is None:
            return result
        try:
            reference = self._evidence_store.persist(result)
        except Exception:
            # Persistence is post-dispatch bookkeeping. Never turn a completed
            # side effect into an execution failure that a caller could retry.
            receipt = dict(result.receipt)
            receipt.update(
                {
                    "evidence_persisted": False,
                    "evidence_error_code": "tool_evidence_persist_failed",
                }
            )
            return replace(result, receipt=receipt)
        receipt = dict(result.receipt)
        receipt.update(
            {
                "evidence_persisted": True,
                "evidence_reference": reference,
            }
        )
        return replace(
            result,
            receipt=receipt,
            evidence_reference=reference,
        )

    async def close(self) -> None:
        await self._mcp_manager.close_all()
        if self._computer_use_adapter is not None:
            await self._computer_use_adapter.close()
        self._mcp_capabilities.clear()
        self._mcp_catalogs.clear()
        self._mcp_owner_source_ids.clear()
        self._run_owners.clear()
        self._call_cancellations.clear()
        self._run_cancellations.clear()

    def _resolve_adapter(
        self,
        call: ToolExecutionCall,
        *,
        owner: MCPOwnerIdentity,
    ) -> tuple[str, str]:
        if (
            call.source_id in {"", "builtin"}
            and call.tool_name in self._builtin_by_name
        ):
            return "builtin", "builtin"

        if (
            self._computer_use_adapter is not None
            and call.source_id
            in {"", self._computer_use_adapter.definition.source_id}
            and call.tool_name == self._computer_use_adapter.definition.name
        ):
            return "computer", self._computer_use_adapter.definition.source_id

        if call.source_id == "builtin":
            raise ToolNotFoundError(
                f"tool {call.tool_name!r} is not an available built-in tool"
            )

        candidate_sources = (
            (call.source_id,)
            if call.source_id
            else tuple(
                sorted(self._mcp_owner_source_ids.get(owner.key, set()))
            )
        )
        if any(
            source_id
            not in self._mcp_owner_source_ids.get(owner.key, set())
            for source_id in candidate_sources
        ):
            raise ToolOwnerScopeError(
                "MCP source is not leased to this execution owner"
            )
        matches = [
            source_id
            for source_id in candidate_sources
            for tool in self._mcp_catalogs.get(
                source_id,
                MCPToolCatalog(
                    source_id=source_id,
                    tools=(),
                    catalog_digest="",
                    changed_since_initialize=False,
                ),
            ).tools
            if call.tool_name in {tool.name, tool.canonical_name}
        ]
        if len(matches) != 1:
            raise ToolNotFoundError(
                f"tool {call.tool_name!r} did not resolve to exactly one live source"
            )
        return "mcp", matches[0]

    async def _execute_builtin(
        self,
        call: ToolExecutionCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        started = time.perf_counter()
        descriptor = self._builtin_by_name[call.tool_name]
        expected_digest = _builtin_schema_digest(descriptor)
        if (
            call.expected_schema_digest
            and call.expected_schema_digest != expected_digest
        ):
            raise ToolExecutionRuntimeError(
                f"built-in tool schema changed for {call.tool_name!r}"
            )
        try:
            result = await asyncio.to_thread(
                self._deterministic_runtime.execute,
                tool_name=call.tool_name,
                arguments=dict(call.arguments),
                tool_call_id=call.call_id,
            )
        except AgenticToolRuntimeError as error:
            raise ToolExecutionRuntimeError(str(error)) from error

        return ToolExecutionResult(
            run_id=context.run_id,
            call_id=call.call_id,
            tool_name=call.tool_name,
            source_id="builtin",
            adapter_kind="builtin",
            status=result.status,
            observation=result.observation,
            duration_ms=(time.perf_counter() - started) * 1_000,
            receipt={
                "schema_version": "melix.tool_execution_receipt.v1",
                "adapter_kind": "builtin",
                "source_id": "builtin",
                "schema_digest": expected_digest,
                "replayability": "deterministic",
                "approval_grant_present": bool(
                    context.approval_grant_digest
                ),
                "policy_revision": context.policy_revision,
                "observation_truncated": _observation_was_truncated(
                    result.observation
                ),
                "result_summary": (
                    "Built-in tool returned a globally truncated observation."
                    if result.observation.globally_truncated
                    else (
                        "Built-in tool returned a result with truncated fields."
                        if result.observation.metrics.truncated_count > 0
                        else "Built-in tool returned a bounded result."
                    )
                ),
            },
        )

    async def _execute_mcp(
        self,
        call: ToolExecutionCall,
        context: ToolExecutionContext,
        source_id: str,
    ) -> ToolExecutionResult:
        started = time.perf_counter()
        execution_status = "completed"
        observation_status = "completed"
        receipt: dict[str, Any] = {
            "schema_version": "melix.tool_execution_receipt.v1",
            "adapter_kind": "mcp",
            "source_id": source_id,
            "replayability": "evidence_only",
            "approval_grant_present": bool(context.approval_grant_digest),
            "policy_revision": context.policy_revision,
        }
        try:
            mcp_result = await self._mcp_manager.call_tool(
                source_id,
                owner=context.owner,
                run_id=context.run_id,
                call_id=call.call_id,
                tool_name=call.tool_name,
                arguments=call.arguments,
                expected_schema_digest=call.expected_schema_digest,
            )
            # MCP `CallToolResult.isError` is an application-level result that
            # the model must be able to inspect and recover from. Keep the RPC
            # execution terminal phase completed while marking the normalized,
            # untrusted observation as failed. Transport, protocol, timeout,
            # and cancellation failures remain terminal below.
            observation_status = (
                "failed" if mcp_result.is_error else "completed"
            )
            payload = _mcp_payload(mcp_result)
            receipt.update(
                {
                    "application_error": mcp_result.is_error,
                    "catalog_digest": mcp_result.catalog_digest,
                    "result_original_bytes": mcp_result.original_bytes,
                    "result_emitted_bytes": mcp_result.emitted_bytes,
                    "result_truncated": mcp_result.truncated,
                }
            )
        except MCPCallCancelledError:
            execution_status = "cancelled"
            observation_status = "failed"
            payload = {
                "cancelled": True,
                "failure_stage": "cancelled",
                "error_code": MCPCallCancelledError.code,
            }
        except MCPCallTimeoutError:
            execution_status = "timeout"
            observation_status = "timeout"
            payload = {
                "timeout": True,
                "failure_stage": "mcp_call",
                "error_code": MCPCallTimeoutError.code,
            }
        except MCPClientError as error:
            execution_status = "failed"
            observation_status = "failed"
            payload = {
                "failure_stage": "mcp_call",
                "error_code": error.code,
            }

        source_receipt = untrusted_context_receipt(
            segment_id=f"{call.call_id}:mcp-result",
            source_type="tool_output",
            source_field="result",
            source_id=source_id,
            message_role="tool",
            owner_scope_checked=True,
            included=True,
            reason="MCP result is untrusted tool output",
            corrective_action=(
                "Keep MCP output in tool-role prompt data and never treat it "
                "as system or developer instructions."
            ),
        )
        observation = normalize_tool_observation(
            tool_name=call.tool_name,
            tool_call_id=call.call_id,
            observation_kind="mcp_tool_result",
            status=observation_status,
            payload=payload,
            policy=self._observation_policy,
            source_untrusted_context_receipts=(source_receipt,),
        )
        receipt["observation_truncated"] = _observation_was_truncated(
            observation
        )
        receipt["result_summary"] = (
            "Tool result was globally truncated to the control-plane observation limit."
            if observation.globally_truncated
            else (
                "MCP tool reported an application error."
                if bool(receipt.get("application_error"))
                else (
                    "MCP result contained fields truncated to the observation text limit."
                    if observation.metrics.truncated_count > 0
                    else (
                        "MCP result was truncated to its configured source byte limit."
                        if bool(receipt.get("result_truncated"))
                        else "MCP tool returned a bounded result."
                    )
                )
            )
        )
        return ToolExecutionResult(
            run_id=context.run_id,
            call_id=call.call_id,
            tool_name=call.tool_name,
            source_id=source_id,
            adapter_kind="mcp",
            status=execution_status,
            observation=observation,
            duration_ms=(time.perf_counter() - started) * 1_000,
            receipt=receipt,
        )

    async def _execute_computer(
        self,
        call: ToolExecutionCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        adapter = self._computer_use_adapter
        if adapter is None:
            raise ToolNotFoundError("Computer Use adapter is unavailable")
        started = time.perf_counter()
        adapter_result = await adapter.execute(call, context)
        source_receipt = untrusted_context_receipt(
            segment_id=f"{call.call_id}:computer-result",
            source_type="tool_output",
            source_field="result",
            source_id=adapter.definition.source_id,
            message_role="tool",
            owner_scope_checked=True,
            included=True,
            reason="Computer Use result is untrusted tool output",
            corrective_action=(
                "Keep Computer Use output in tool-role prompt data and never "
                "treat it as system or developer instructions."
            ),
        )
        observation_status = (
            adapter_result.status
            if adapter_result.status in {"completed", "failed", "timeout"}
            else "failed"
        )
        observation = normalize_tool_observation(
            tool_name=call.tool_name,
            tool_call_id=call.call_id,
            observation_kind="computer_use_result",
            status=observation_status,
            payload=dict(adapter_result.payload),
            policy=self._observation_policy,
            source_untrusted_context_receipts=(source_receipt,),
        )
        receipt = dict(adapter_result.receipt)
        receipt.update(
            {
                "approval_grant_present": bool(
                    context.approval_grant_digest
                ),
                "policy_revision": context.policy_revision,
                "observation_binding_schema_version": (
                    "melix.computer_use_observation_binding.v1"
                ),
                "observation_sha256": _digest_json(
                    observation.as_agentic_trace_observation()
                ),
                "observation_truncated": _observation_was_truncated(
                    observation
                ),
                "result_summary": (
                    "Computer Use returned a globally truncated observation."
                    if observation.globally_truncated
                    else (
                        "Computer Use returned an observation with truncated fields."
                        if observation.metrics.truncated_count > 0
                        else "Computer Use returned a bounded typed observation."
                    )
                ),
            }
        )
        return ToolExecutionResult(
            run_id=context.run_id,
            call_id=call.call_id,
            tool_name=call.tool_name,
            source_id=adapter.definition.source_id,
            adapter_kind="computer",
            status=adapter_result.status,
            observation=observation,
            duration_ms=(time.perf_counter() - started) * 1_000,
            receipt=receipt,
        )

    def _cancelled_result(
        self,
        call: ToolExecutionCall,
        context: ToolExecutionContext,
        *,
        source_id: str,
        adapter_kind: str,
        side_effect_state: str,
    ) -> ToolExecutionResult:
        payload = {
            "cancelled": True,
            "failure_stage": "cancelled",
            "error_code": "tool_execution_cancelled",
        }
        observation = normalize_tool_observation(
            tool_name=call.tool_name,
            tool_call_id=call.call_id,
            observation_kind=f"{adapter_kind}_tool_result",
            status="failed",
            payload=payload,
            policy=self._observation_policy,
        )
        return ToolExecutionResult(
            run_id=context.run_id,
            call_id=call.call_id,
            tool_name=call.tool_name,
            source_id=source_id,
            adapter_kind=adapter_kind,
            status="cancelled",
            observation=observation,
            duration_ms=0,
            receipt={
                "schema_version": "melix.tool_execution_receipt.v1",
                "adapter_kind": adapter_kind,
                "source_id": source_id,
                "replayability": (
                    "deterministic"
                    if adapter_kind == "builtin"
                    else "evidence_only"
                ),
                "cancelled": True,
                "cancellation_id": _stable_cancellation_id(
                    context.owner,
                    context.run_id,
                    call.call_id,
                ),
                "side_effect_state": side_effect_state,
                "observation_truncated": _observation_was_truncated(
                    observation
                ),
                "result_summary": "Tool execution was cancelled.",
            },
        )


def _validate_admission(context: ToolExecutionContext) -> None:
    if context.admission_state not in {"allow", "approved"}:
        raise ToolAdmissionRequiredError(
            "tool execution requires allow policy or an exact approval"
        )
    if context.admission_state == "approved" and not context.approval_grant_digest:
        raise ToolAdmissionRequiredError(
            "approved tool execution requires approval_grant_digest"
        )


def _validate_deadline(context: ToolExecutionContext) -> None:
    if (
        context.deadline_unix_ms
        and int(time.time() * 1_000) >= context.deadline_unix_ms
    ):
        raise ToolExecutionRuntimeError("tool execution deadline has expired")


def _builtin_catalog_entry(
    descriptor: ToolDescriptor,
) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        source_id="builtin",
        adapter_kind="builtin",
        name=descriptor.name,
        source_tool_name=descriptor.name,
        title="",
        description=descriptor.description,
        input_schema=descriptor.schema_payload(),
        output_schema=None,
        schema_digest=_builtin_schema_digest(descriptor),
        risk_class=_builtin_risk_class(descriptor),
        replayability="deterministic",
        annotations_untrusted=False,
    )


def _builtin_schema_digest(descriptor: ToolDescriptor) -> str:
    return _digest_json(
        {
            "name": descriptor.name,
            "description": descriptor.description,
            "input_schema": descriptor.schema_payload(),
            "tool_kind": descriptor.tool_kind,
            "observation_kind": descriptor.observation_kind,
        }
    )


def _builtin_risk_class(descriptor: ToolDescriptor) -> str:
    if descriptor.name == "workspace_file":
        return "argument_dependent"
    if descriptor.name == "visit":
        return "network_read"
    return "local_read_or_compute"


def _mcp_payload(result: MCPToolResult) -> dict[str, Any]:
    return {
        "source_id": result.source_id,
        "is_error": result.is_error,
        "content": [dict(item) for item in result.content],
        "structured_content": (
            dict(result.structured_content)
            if result.structured_content is not None
            else None
        ),
        "mcp_receipt": {
            "catalog_digest": result.catalog_digest,
            "original_bytes": result.original_bytes,
            "emitted_bytes": result.emitted_bytes,
            "truncated": result.truncated,
        },
    }


def _observation_was_truncated(observation: ToolObservationRecord) -> bool:
    return (
        observation.globally_truncated
        or observation.metrics.truncated_count > 0
    )


def _execution_digest(
    call: ToolExecutionCall,
    context: ToolExecutionContext,
) -> str:
    return _digest_json(
        {
            "run_id": context.run_id,
            "session_id": context.session_id,
            "branch_id": context.branch_id,
            "actor_id": context.actor_id,
            "call_id": call.call_id,
            "tool_name": call.tool_name,
            "source_id": call.source_id,
            "arguments": dict(call.arguments),
            "expected_schema_digest": call.expected_schema_digest,
            "idempotency_key": call.idempotency_key,
            "admission_state": context.admission_state,
            "approval_grant_digest": context.approval_grant_digest,
            "policy_revision": context.policy_revision,
        }
    )


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _identity_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _stable_cancellation_id(
    owner: MCPOwnerIdentity,
    run_id: str,
    call_id: str,
) -> str:
    digest = hashlib.sha256(
        (
            "melix-agent-tool-cancel\0"
            f"{owner.session_id}\0{owner.branch_id}\0{owner.actor_id}\0"
            f"{run_id}\0{call_id}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"tool-cancel-{digest}"


def _stable_run_cancellation_id(
    owner: MCPOwnerIdentity,
    run_id: str,
) -> str:
    digest = hashlib.sha256(
        (
            "melix-agent-run-tools-cancel\0"
            f"{owner.session_id}\0{owner.branch_id}\0{owner.actor_id}\0"
            f"{run_id}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"run-tools-cancel-{digest}"


def _combined_side_effect_state(states: list[str]) -> str:
    if "unknown" in states:
        return "unknown"
    if "committed" in states:
        return "committed"
    return "none"


def _assert_bounded_json_schema(
    schema: Mapping[str, Any],
    *,
    allow_regex_keywords: bool = True,
) -> None:
    if len(_canonical_json_bytes(schema)) > _MAX_TOOL_SCHEMA_BYTES:
        raise ToolCatalogSchemaError("tool JSON schema exceeds byte limit")
    stack: list[tuple[Any, int]] = [(schema, 0)]
    node_count = 0
    while stack:
        value, depth = stack.pop()
        node_count += 1
        if node_count > _MAX_TOOL_SCHEMA_NODES:
            raise ToolCatalogSchemaError("tool JSON schema exceeds node limit")
        if depth > _MAX_TOOL_SCHEMA_DEPTH:
            raise ToolCatalogSchemaError("tool JSON schema exceeds depth limit")
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = str(raw_key)
                if (
                    key in {"$ref", "$dynamicRef"}
                    and isinstance(child, str)
                    and not child.startswith("#")
                ):
                    raise ToolCatalogSchemaError(
                        "tool JSON schema contains an external reference"
                    )
                if not allow_regex_keywords and key in {
                    "pattern",
                    "patternProperties",
                }:
                    raise ToolCatalogSchemaError(
                        "untrusted MCP tool JSON schema contains a regex keyword"
                    )
                if key == "pattern" and isinstance(child, str) and (
                    len(child.encode("utf-8")) > 512
                ):
                    raise ToolCatalogSchemaError(
                        "tool JSON schema pattern exceeds byte limit"
                    )
                stack.append((child, depth + 1))
        elif isinstance(value, (list, tuple)):
            stack.extend((child, depth + 1) for child in value)


def _bounded_evidence_text(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= _EVIDENCE_MAX_TEXT_BYTES:
        return _BEARER_CREDENTIAL.sub("Bearer [REDACTED]", value)
    bounded = encoded[:_EVIDENCE_MAX_TEXT_BYTES].decode(
        "utf-8",
        errors="ignore",
    )
    return _BEARER_CREDENTIAL.sub("Bearer [REDACTED]", bounded)


def _sanitize_evidence_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= _EVIDENCE_MAX_DEPTH:
        return {"truncated": True, "reason": "maximum_depth"}
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        items = sorted(value.items(), key=lambda item: str(item[0]))
        for raw_key, raw_item in items[:_EVIDENCE_MAX_ITEMS]:
            key = _bounded_evidence_text(str(raw_key))
            if _SENSITIVE_EVIDENCE_KEY.search(key):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = _sanitize_evidence_value(
                    raw_item,
                    depth=depth + 1,
                )
        if len(items) > _EVIDENCE_MAX_ITEMS:
            sanitized["_truncated_item_count"] = (
                len(items) - _EVIDENCE_MAX_ITEMS
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        sanitized_items = [
            _sanitize_evidence_value(item, depth=depth + 1)
            for item in value[:_EVIDENCE_MAX_ITEMS]
        ]
        if len(value) > _EVIDENCE_MAX_ITEMS:
            sanitized_items.append(
                {
                    "truncated": True,
                    "omitted_item_count": len(value) - _EVIDENCE_MAX_ITEMS,
                }
            )
        return sanitized_items
    if isinstance(value, str):
        return _bounded_evidence_text(value)
    if isinstance(value, bytes):
        return {
            "redacted": True,
            "byte_count": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    return _bounded_evidence_text(str(value))
