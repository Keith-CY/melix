from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import anyio
import httpx
import mcp.types as mcp_types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import (
    PROCESS_TERMINATION_TIMEOUT,
    _create_platform_compatible_process,
    _get_executable_command,
    _terminate_process_tree,
    get_default_environment,
)
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.message import SessionMessage

from worker.productization.mcp_credential_environment import (
    MCP_CREDENTIAL_KEYS_ENV,
    MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS,
    MCP_HTTP_HEADER_NAME_PATTERN,
    MAX_MCP_CREDENTIAL_KEY_LIST_BYTES,
    MAX_MCP_CREDENTIAL_KEY_BYTES,
    MAX_MCP_CREDENTIAL_REFERENCES,
    MAX_MCP_REFERENCE_TARGET_BYTES,
    MAX_MCP_REFERENCE_TARGET_LIST_BYTES,
    bounded_mcp_credential_environment_key_union,
)


_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_CANONICAL_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_MAX_CATALOG_PAGES = 32
_MAX_CATALOG_TOOLS = 512
_MAX_CATALOG_BYTES = 2 * 1_024 * 1_024
_MAX_TOOL_DEFINITION_BYTES = 256 * 1_024
_MAX_SERVER_METADATA_BYTES = 256 * 1_024
_SOURCE_CLOSE_TIMEOUT_SECONDS = 5.0
_CANCEL_PROPAGATION_TIMEOUT_SECONDS = 0.25
_DEFAULT_SOURCE_LEASE_SECONDS = 300.0
_MAX_SOURCE_LEASE_SECONDS = 3_600.0
_MAX_RESULT_BYTES = 16 * 1_024 * 1_024
_MAX_RESULT_DEPTH = 24
_MAX_RESULT_NODES = 4_096
# A wire message must accommodate the largest supported result plus JSON-RPC
# framing, while still placing a hard ceiling before JSON/Pydantic parsing.
_MAX_MCP_WIRE_MESSAGE_BYTES = 20 * 1_024 * 1_024
_SSE_NEWLINE_BYTE_PATTERN = re.compile(br"[\r\n]")
_CREDENTIAL_HEADER_PATTERN = re.compile(
    r"(?:authorization|cookie|credential|password|private[_-]?key|"
    r"secret|signature|token|api[_-]?key)",
    re.IGNORECASE,
)


class MCPClientError(RuntimeError):
    code = "mcp_client_error"


class MCPSourceConfigurationError(MCPClientError):
    code = "mcp_source_configuration_invalid"


class MCPSourceNotInitializedError(MCPClientError):
    code = "mcp_source_not_initialized"


class MCPSourceOwnershipError(MCPClientError):
    code = "mcp_source_owner_scope_mismatch"


def _validate_environment_references(
    references: Mapping[str, str],
    *,
    transport_name: str,
) -> None:
    if len(references) > MAX_MCP_CREDENTIAL_REFERENCES:
        raise MCPSourceConfigurationError(
            f"MCP {transport_name} environment references exceed the limit"
        )
    raw_source_keys = tuple(references.values())
    if any(not isinstance(key, str) for key in raw_source_keys):
        raise MCPSourceConfigurationError(
            f"invalid environment reference for MCP {transport_name} source"
        )
    source_keys = set(raw_source_keys)
    source_key_bytes = sum(len(key.encode("utf-8")) for key in source_keys)
    source_key_bytes += max(0, len(source_keys) - 1)
    target_key_bytes = sum(
        len(key.encode("utf-8"))
        for key in references
        if isinstance(key, str)
    ) + max(0, len(references) - 1)
    if (
        source_key_bytes > MAX_MCP_CREDENTIAL_KEY_LIST_BYTES
        or target_key_bytes > MAX_MCP_REFERENCE_TARGET_LIST_BYTES
    ):
        raise MCPSourceConfigurationError(
            f"MCP {transport_name} environment references exceed the byte limit"
        )
    for child_key, source_key in references.items():
        if transport_name == "stdio" and (
            not isinstance(child_key, str)
            or not _ENVIRONMENT_KEY_PATTERN.fullmatch(child_key)
            or len(child_key.encode("utf-8")) > MAX_MCP_REFERENCE_TARGET_BYTES
        ):
            raise MCPSourceConfigurationError(
                f"invalid child environment key for MCP stdio source: {child_key!r}"
            )
        if transport_name == "HTTP" and (
            not isinstance(child_key, str)
            or not MCP_HTTP_HEADER_NAME_PATTERN.fullmatch(child_key)
            or len(child_key.encode("utf-8")) > MAX_MCP_REFERENCE_TARGET_BYTES
        ):
            raise MCPSourceConfigurationError(
                "MCP HTTP credential header names must not be blank"
            )
        if (
            not isinstance(source_key, str)
            or not _ENVIRONMENT_KEY_PATTERN.fullmatch(source_key)
            or len(source_key.encode("utf-8")) > MAX_MCP_CREDENTIAL_KEY_BYTES
        ):
            raise MCPSourceConfigurationError(
                f"invalid environment reference for MCP {transport_name} source: "
                f"{source_key!r}"
            )
        if source_key in MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS:
            raise MCPSourceConfigurationError(
                f"MCP {transport_name} environment reference uses a reserved "
                "Melix process key"
            )


def _validate_http_header_names(headers: Mapping[str, str]) -> None:
    if len(headers) > MAX_MCP_CREDENTIAL_REFERENCES:
        raise MCPSourceConfigurationError("MCP HTTP headers exceed the limit")
    encoded_bytes = sum(
        len(name.encode("utf-8"))
        for name in headers
        if isinstance(name, str)
    ) + max(0, len(headers) - 1)
    if encoded_bytes > MAX_MCP_REFERENCE_TARGET_LIST_BYTES:
        raise MCPSourceConfigurationError("MCP HTTP headers exceed the byte limit")
    for name, value in headers.items():
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or len(name.encode("utf-8")) > MAX_MCP_REFERENCE_TARGET_BYTES
            or not MCP_HTTP_HEADER_NAME_PATTERN.fullmatch(name)
        ):
            raise MCPSourceConfigurationError("MCP HTTP header name is invalid")


class MCPConnectionError(MCPClientError):
    code = "mcp_connection_failed"


class MCPWireLimitError(MCPConnectionError):
    code = "mcp_wire_limit_exceeded"


class MCPToolNotFoundError(MCPClientError):
    code = "mcp_tool_not_found"


class MCPToolSchemaChangedError(MCPClientError):
    code = "mcp_tool_schema_changed"


class MCPCallCancelledError(MCPClientError):
    code = "mcp_call_cancelled"


class MCPCallTimeoutError(MCPClientError):
    code = "mcp_call_timeout"


@dataclass(frozen=True)
class MCPOwnerIdentity:
    session_id: str
    branch_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("session_id", self.session_id),
            ("branch_id", self.branch_id),
            ("actor_id", self.actor_id),
        ):
            normalized = value.strip()
            if not normalized:
                raise MCPSourceOwnershipError(
                    f"MCP owner {field_name} must not be blank"
                )
            if "\x00" in value or len(value.encode("utf-8")) > 256:
                raise MCPSourceOwnershipError(
                    f"MCP owner {field_name} is invalid"
                )

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.session_id, self.branch_id, self.actor_id)


@dataclass(frozen=True)
class _MCPSourceLease:
    owner: MCPOwnerIdentity
    configuration_digest: str
    expires_at_monotonic: float


@dataclass(frozen=True)
class MCPStdioTransport:
    command: str
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None
    environment_references: Mapping[str, str] = field(default_factory=dict)

    def resolved_environment(
        self,
        environment: Mapping[str, str],
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for child_key, source_key in sorted(self.environment_references.items()):
            if not _ENVIRONMENT_KEY_PATTERN.fullmatch(child_key):
                raise MCPSourceConfigurationError(
                    f"invalid child environment key for MCP stdio source: {child_key!r}"
                )
            if not _ENVIRONMENT_KEY_PATTERN.fullmatch(source_key):
                raise MCPSourceConfigurationError(
                    f"invalid environment reference for MCP stdio source: {source_key!r}"
                )
            value = environment.get(source_key)
            if value is not None:
                resolved[child_key] = value
        return resolved


@dataclass(frozen=True)
class MCPStreamableHTTPTransport:
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    header_environment_references: Mapping[str, str] = field(default_factory=dict)

    def resolved_headers(
        self,
        environment: Mapping[str, str],
    ) -> dict[str, str]:
        resolved = {
            key.strip(): value
            for key, value in self.headers.items()
            if key.strip()
        }
        for header, source_key in sorted(self.header_environment_references.items()):
            normalized_header = header.strip()
            if not normalized_header:
                raise MCPSourceConfigurationError(
                    "MCP HTTP credential header names must not be blank"
                )
            if not _ENVIRONMENT_KEY_PATTERN.fullmatch(source_key):
                raise MCPSourceConfigurationError(
                    f"invalid environment reference for MCP HTTP source: {source_key!r}"
                )
            value = environment.get(source_key)
            if value is not None:
                resolved[normalized_header] = value
        return resolved


MCPTransport = MCPStdioTransport | MCPStreamableHTTPTransport


def _source_credential_environment_keys(
    source: "MCPSourceDefinition",
) -> frozenset[str]:
    if isinstance(source.transport, MCPStdioTransport):
        return frozenset(source.transport.environment_references.values())
    return frozenset(
        source.transport.header_environment_references.values()
    )


@dataclass(frozen=True)
class MCPSourceDefinition:
    source_id: str
    transport: MCPTransport
    request_timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 15.0
    max_result_bytes: int = 262_144
    redaction_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise MCPSourceConfigurationError(
                "MCP source_id must match ^[a-z0-9][a-z0-9_-]{0,63}$"
            )
        if self.request_timeout_seconds <= 0:
            raise MCPSourceConfigurationError(
                "MCP request_timeout_seconds must be positive"
            )
        if self.connect_timeout_seconds <= 0:
            raise MCPSourceConfigurationError(
                "MCP connect_timeout_seconds must be positive"
            )
        if self.max_result_bytes < 1_024:
            raise MCPSourceConfigurationError(
                "MCP max_result_bytes must be at least 1024"
            )
        if self.max_result_bytes > _MAX_RESULT_BYTES:
            raise MCPSourceConfigurationError(
                "MCP max_result_bytes must be no more than 16777216"
            )

        if isinstance(self.transport, MCPStdioTransport):
            _validate_environment_references(
                self.transport.environment_references,
                transport_name="stdio",
            )
            if not self.transport.command.strip():
                raise MCPSourceConfigurationError(
                    "MCP stdio command must not be blank"
                )
            if "\x00" in self.transport.command:
                raise MCPSourceConfigurationError(
                    "MCP stdio command must not contain NUL"
                )
            if self.transport.working_directory is not None:
                if not os.path.isabs(self.transport.working_directory):
                    raise MCPSourceConfigurationError(
                        "MCP stdio working_directory must be absolute"
                    )
        else:
            _validate_http_header_names(self.transport.headers)
            _validate_environment_references(
                self.transport.header_environment_references,
                transport_name="HTTP",
            )
            http_header_names = (
                *self.transport.headers.keys(),
                *self.transport.header_environment_references.keys(),
            )
            encoded_http_header_name_bytes = sum(
                len(name.encode("utf-8")) for name in http_header_names
            ) + max(0, len(http_header_names) - 1)
            if (
                len(http_header_names) > MAX_MCP_CREDENTIAL_REFERENCES
                or encoded_http_header_name_bytes
                > MAX_MCP_REFERENCE_TARGET_LIST_BYTES
                or len({name.lower() for name in http_header_names})
                != len(http_header_names)
            ):
                raise MCPSourceConfigurationError(
                    "MCP HTTP header names conflict or exceed the transport limit"
                )
            parsed = urlparse(self.transport.url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise MCPSourceConfigurationError(
                    "MCP Streamable HTTP URL must be an absolute http(s) URL"
                )
            if parsed.username is not None or parsed.password is not None:
                raise MCPSourceConfigurationError(
                    "MCP Streamable HTTP URL must not contain userinfo"
                )
            if "#" in self.transport.url:
                raise MCPSourceConfigurationError(
                    "MCP Streamable HTTP URL must not contain a fragment"
                )
            if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
                raise MCPSourceConfigurationError(
                    "unencrypted MCP HTTP is allowed only for loopback hosts"
                )
            static_credential_headers = sorted(
                header.strip()
                for header in self.transport.headers
                if _CREDENTIAL_HEADER_PATTERN.search(header.strip())
            )
            if static_credential_headers:
                raise MCPSourceConfigurationError(
                    "MCP HTTP credential headers must use environment references"
                )

    @property
    def transport_kind(self) -> str:
        if isinstance(self.transport, MCPStdioTransport):
            return "stdio"
        return "streamable_http"

    @property
    def configuration_digest(self) -> str:
        if isinstance(self.transport, MCPStdioTransport):
            transport_payload: dict[str, Any] = {
                "kind": "stdio",
                "command": self.transport.command,
                "arguments": list(self.transport.arguments),
                "working_directory": self.transport.working_directory,
                "environment_keys": sorted(self.transport.environment_references),
            }
        else:
            transport_payload = {
                "kind": "streamable_http",
                "url": self.transport.url,
                "header_names": sorted(
                    set(self.transport.headers)
                    | set(self.transport.header_environment_references)
                ),
            }
        return _digest_json(
            {
                "source_id": self.source_id,
                "transport": transport_payload,
                "request_timeout_seconds": self.request_timeout_seconds,
                "connect_timeout_seconds": self.connect_timeout_seconds,
                "max_result_bytes": self.max_result_bytes,
            }
        )


@dataclass(frozen=True)
class MCPToolDefinition:
    source_id: str
    name: str
    canonical_name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    annotations: Mapping[str, Any]
    schema_digest: str


@dataclass(frozen=True)
class MCPServerCapabilities:
    source_id: str
    transport_kind: str
    protocol_version: str
    server_name: str
    server_version: str
    capability_names: tuple[str, ...]
    tool_count: int
    catalog_digest: str
    connected_at_unix_ms: int


@dataclass(frozen=True)
class MCPToolCatalog:
    source_id: str
    tools: tuple[MCPToolDefinition, ...]
    catalog_digest: str
    changed_since_initialize: bool


@dataclass(frozen=True)
class MCPToolResult:
    source_id: str
    tool_name: str
    call_id: str
    content: tuple[Mapping[str, Any], ...]
    structured_content: Mapping[str, Any] | None
    is_error: bool
    original_bytes: int
    emitted_bytes: int
    truncated: bool
    duration_ms: float
    catalog_digest: str


@dataclass(frozen=True)
class MCPCancellationReceipt:
    source_id: str
    run_id: str
    call_id: str
    disposition: str
    side_effect_state: str
    # True only when an active SDK request task has reached a cancellation
    # terminal. Queued cancellation and lookup-only receipts intentionally do
    # not satisfy the propagation boundary.
    propagation_acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class MCPOperationMetricsSnapshot:
    invocation_count: int
    failure_count: int
    total_latency_ms: float
    last_latency_ms: float
    maximum_latency_ms: float

    @property
    def average_latency_ms(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return self.total_latency_ms / self.invocation_count


@dataclass(frozen=True, slots=True)
class MCPClientMetricsSnapshot:
    schema_version: str
    initialize: MCPOperationMetricsSnapshot
    list_tools: MCPOperationMetricsSnapshot
    call_tool: MCPOperationMetricsSnapshot
    cancel_propagation: MCPOperationMetricsSnapshot
    reconnect_count: int
    schema_change_count: int


@dataclass(slots=True)
class _MutableMCPOperationMetrics:
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
class _ListCommand:
    refresh: bool
    response: asyncio.Future[MCPToolCatalog]


@dataclass
class _CallCommand:
    owner: MCPOwnerIdentity
    run_id: str
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    expected_schema_digest: str
    response: asyncio.Future[MCPToolResult]


@dataclass
class _CloseCommand:
    response: asyncio.Future[None]


_ActorCommand = _ListCommand | _CallCommand | _CloseCommand


class _MCPSourceActor:
    def __init__(
        self,
        source: MCPSourceDefinition,
        *,
        environment: Mapping[str, str],
    ) -> None:
        self.source = source
        self._environment = dict(environment)
        self._redaction_terms = _resolved_redaction_terms(
            source,
            self._environment,
        )
        self._commands: asyncio.Queue[_ActorCommand] = asyncio.Queue()
        self._ready: asyncio.Future[MCPServerCapabilities] | None = None
        self._task: asyncio.Task[None] | None = None
        self._failure: MCPConnectionError | None = None
        self._closing = False
        self._active_call_key: tuple[
            tuple[str, str, str], str, str
        ] | None = None
        self._active_call_task: asyncio.Task[Any] | None = None
        self._queued_call_keys: set[
            tuple[tuple[str, str, str], str, str]
        ] = set()
        self._cancelled_call_keys: set[
            tuple[tuple[str, str, str], str, str]
        ] = set()
        # A dict gives us set-like membership plus insertion order. Retention
        # must evict the oldest terminal calls; lexical set sorting can discard
        # a just-completed call immediately and break bounded cancellation
        # idempotency.
        self._terminal_call_keys: dict[
            tuple[tuple[str, str, str], str, str], None
        ] = {}
        self._catalog = MCPToolCatalog(
            source_id=source.source_id,
            tools=(),
            catalog_digest=_digest_json([]),
            changed_since_initialize=False,
        )
        self._catalog_stale = False
        self._catalog_changed_since_initialize = False

    async def start(self) -> MCPServerCapabilities:
        if self._task is not None:
            assert self._ready is not None
            if self._task.done() and self._failure is not None:
                raise self._failure
            return await self._ready
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        self._ready.add_done_callback(_observe_future_exception)
        self._task = asyncio.create_task(
            self._run(),
            name=f"melix-mcp-{self.source.source_id}",
        )
        try:
            return await asyncio.wait_for(
                asyncio.shield(self._ready),
                timeout=self.source.connect_timeout_seconds,
            )
        except TimeoutError as error:
            await self.force_close()
            raise MCPConnectionError(
                f"MCP source {self.source.source_id!r} initialization timed out"
            ) from error

    async def list_tools(self, *, refresh: bool = False) -> MCPToolCatalog:
        if self._closing:
            raise MCPConnectionError(
                f"MCP source {self.source.source_id!r} is closing"
            )
        response = asyncio.get_running_loop().create_future()
        response.add_done_callback(_observe_future_exception)
        await self._commands.put(
            _ListCommand(refresh=refresh, response=response)
        )
        return await self._await_response(response)

    async def call_tool(
        self,
        *,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        expected_schema_digest: str,
    ) -> MCPToolResult:
        if self._closing:
            raise MCPConnectionError(
                f"MCP source {self.source.source_id!r} is closing"
            )
        response = asyncio.get_running_loop().create_future()
        response.add_done_callback(_observe_future_exception)
        call_key = (owner.key, run_id, call_id)
        self._queued_call_keys.add(call_key)
        await self._commands.put(
            _CallCommand(
                owner=owner,
                run_id=run_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                expected_schema_digest=expected_schema_digest,
                response=response,
            )
        )
        return await self._await_response(response)

    @property
    def is_live(self) -> bool:
        return (
            self._task is not None
            and not self._task.done()
            and self._ready is not None
            and self._ready.done()
            and self._failure is None
        )

    async def cancel(
        self,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
    ) -> MCPCancellationReceipt:
        call_key = (owner.key, run_id, call_id)
        if (
            call_key == self._active_call_key
            and self._active_call_task is not None
        ):
            if self._active_call_task.done():
                return MCPCancellationReceipt(
                    source_id=self.source.source_id,
                    run_id=run_id,
                    call_id=call_id,
                    disposition="already_terminal",
                    side_effect_state="unknown",
                )
            active_call_task = self._active_call_task
            active_call_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(active_call_task),
                    timeout=_CANCEL_PROPAGATION_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
            except TimeoutError:
                pass
            except BaseException:
                # A concurrent transport failure is terminal but does not prove
                # that cancellation reached the SDK request task.
                pass
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                # MCP has no portable commit-point receipt. Once tools/call was
                # dispatched, cancellation cannot truthfully claim that no
                # server-side side effect occurred.
                side_effect_state="unknown",
                propagation_acknowledged=active_call_task.cancelled(),
            )
        if call_key in self._queued_call_keys:
            self._cancelled_call_keys.add(call_key)
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                side_effect_state="none",
            )
        if call_key in self._terminal_call_keys:
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="already_terminal",
                side_effect_state="unknown",
            )
        matching_identity_keys = (
            set(self._queued_call_keys)
            | set(self._terminal_call_keys)
            | ({self._active_call_key} if self._active_call_key else set())
        )
        if any(
            key[0] != owner.key and key[1:] == (run_id, call_id)
            for key in matching_identity_keys
        ):
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="scope_mismatch",
                side_effect_state="unknown",
            )
        return MCPCancellationReceipt(
            source_id=self.source.source_id,
            run_id=run_id,
            call_id=call_id,
            disposition="not_found",
            side_effect_state="unknown",
        )

    async def cancel_owner(self, owner: MCPOwnerIdentity) -> None:
        owner_key = owner.key
        active_key = self._active_call_key
        if (
            active_key is not None
            and active_key[0] == owner_key
            and self._active_call_task is not None
            and not self._active_call_task.done()
        ):
            self._active_call_task.cancel()
        self._cancelled_call_keys.update(
            key for key in self._queued_call_keys if key[0] == owner_key
        )

    async def close(self) -> None:
        await self.force_close()

    async def force_close(self) -> None:
        task = self._task
        if task is None or task.done():
            return

        self._closing = True
        self._fail_pending_commands(
            MCPConnectionError(
                f"MCP source {self.source.source_id!r} is closing"
            )
        )

        # Let the actor unwind its MCP transport context normally whenever it
        # still owns a responsive command loop.  Cancelling the actor task
        # directly also cancels the stdio transport's shutdown awaits, which
        # can strand the child process and keep the task alive past our bound.
        # Cancelling only the in-flight call lets the actor return to the loop
        # and consume the close command without dispatching any queued work.
        active_call_task = self._active_call_task
        if active_call_task is not None and not active_call_task.done():
            active_call_task.cancel()
        response = asyncio.get_running_loop().create_future()
        response.add_done_callback(_observe_future_exception)
        await self._commands.put(_CloseCommand(response=response))
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=_SOURCE_CLOSE_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            # Awaiting a target task which accepted cancellation also raises
            # CancelledError. Suppress only that expected target result; never
            # swallow cancellation of the force_close caller itself.
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                task.cancel()
                raise
        except TimeoutError as error:
            # A wedged initialization/transport must not make shutdown
            # unbounded.  Request hard cancellation before returning the
            # bounded failure to the caller; do not wait on a task that has
            # already demonstrated that it will not cooperate.
            task.cancel()
            raise MCPConnectionError(
                f"MCP source {self.source.source_id!r} did not close within "
                f"{_SOURCE_CLOSE_TIMEOUT_SECONDS:g} seconds"
            ) from error
        except MCPConnectionError:
            # A transport failure is already terminal and therefore satisfies
            # forced shutdown.
            return

    async def _run(self) -> None:
        assert self._ready is not None
        try:
            transport_context = self._transport_context()
            async with transport_context as streams:
                read_stream, write_stream, wire_failure = streams
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(
                        seconds=self.source.connect_timeout_seconds
                    ),
                    message_handler=self._handle_message,
                ) as session:
                    initialized = await _await_with_wire_failure(
                        session.initialize(),
                        wire_failure,
                    )
                    self._catalog = await _await_with_wire_failure(
                        self._load_catalog(session),
                        wire_failure,
                    )
                    capabilities = _server_capabilities(
                        self.source,
                        initialized,
                        self._catalog,
                        redaction_terms=self._redaction_terms,
                    )
                    self._ready.set_result(capabilities)
                    await _await_with_wire_failure(
                        self._command_loop(session),
                        wire_failure,
                    )
        except BaseException as error:
            wire_failure = _find_wire_limit_error(error)
            if wire_failure is not None:
                self._failure = wire_failure
            else:
                self._failure = MCPConnectionError(
                    f"MCP source {self.source.source_id!r} connection closed"
                )
                self._failure.__cause__ = error
            if not self._ready.done():
                if wire_failure is None:
                    self._failure = MCPConnectionError(
                        f"MCP source {self.source.source_id!r} failed to initialize"
                    )
                    self._failure.__cause__ = error
                self._ready.set_exception(self._failure)
            self._fail_pending_commands(self._failure)
            if (
                isinstance(error, asyncio.CancelledError)
                and wire_failure is None
            ):
                raise

    async def _await_response(self, response: asyncio.Future[Any]) -> Any:
        task = self._task
        if task is None:
            raise MCPSourceNotInitializedError(
                f"MCP source {self.source.source_id!r} is not initialized"
            )
        try:
            completed, _ = await asyncio.wait(
                {response, task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            if not response.done():
                response.cancel()
            raise
        if response in completed:
            return await response
        if not response.done():
            response.cancel()
        raise self._failure or MCPConnectionError(
            f"MCP source {self.source.source_id!r} connection closed"
        )

    def _transport_context(
        self,
    ) -> AbstractAsyncContextManager[tuple[Any, ...]]:
        transport = self.source.transport
        if isinstance(transport, MCPStdioTransport):
            parameters = StdioServerParameters(
                command=transport.command,
                args=list(transport.arguments),
                env=transport.resolved_environment(self._environment),
                cwd=transport.working_directory,
            )
            return _bounded_stdio_transport(
                parameters,
                source_id=self.source.source_id,
                max_message_bytes=_MAX_MCP_WIRE_MESSAGE_BYTES,
            )

        return _streamable_http_transport(
            transport.url,
            source_id=self.source.source_id,
            headers=transport.resolved_headers(self._environment),
            timeout=self.source.request_timeout_seconds,
            max_message_bytes=_MAX_MCP_WIRE_MESSAGE_BYTES,
        )

    async def _command_loop(self, session: ClientSession) -> None:
        while True:
            command = await self._commands.get()
            if isinstance(command, _CloseCommand):
                if not command.response.done():
                    command.response.set_result(None)
                return
            if isinstance(command, _ListCommand):
                await self._handle_list_command(session, command)
                continue
            await self._handle_call_command(session, command)

    async def _handle_list_command(
        self,
        session: ClientSession,
        command: _ListCommand,
    ) -> None:
        try:
            if command.refresh:
                self._catalog_stale = True
            if self._catalog_stale:
                self._catalog = await self._load_catalog(session)
            if not command.response.done():
                command.response.set_result(self._catalog)
        except asyncio.CancelledError:
            raise
        except MCPClientError as error:
            if not command.response.done():
                command.response.set_exception(error)
        except BaseException as error:
            connection_error = MCPConnectionError(
                f"MCP source {self.source.source_id!r} catalog request failed"
            )
            if not command.response.done():
                command.response.set_exception(connection_error)
            raise connection_error from error

    async def _handle_call_command(
        self,
        session: ClientSession,
        command: _CallCommand,
    ) -> None:
        started = time.perf_counter()
        call_key = (command.owner.key, command.run_id, command.call_id)
        self._queued_call_keys.discard(call_key)
        self._active_call_key = call_key
        try:
            if command.response.cancelled():
                return
            if call_key in self._cancelled_call_keys:
                raise MCPCallCancelledError(
                    f"MCP call {command.call_id!r} was cancelled before dispatch"
                )
            if self._catalog_stale:
                self._catalog = await self._load_catalog(session)
            tool = self._resolve_tool(command.tool_name)
            if (
                command.expected_schema_digest
                and command.expected_schema_digest != tool.schema_digest
            ):
                raise MCPToolSchemaChangedError(
                    f"MCP tool schema changed for {tool.canonical_name!r}"
                )

            self._active_call_task = asyncio.create_task(
                session.call_tool(
                    tool.name,
                    arguments=dict(command.arguments),
                    read_timeout_seconds=timedelta(
                        seconds=self.source.request_timeout_seconds
                    ),
                ),
                name=f"melix-mcp-call-{command.call_id}",
            )
            try:
                raw_result = await asyncio.wait_for(
                    asyncio.shield(self._active_call_task),
                    timeout=self.source.request_timeout_seconds,
                )
            except asyncio.CancelledError as error:
                if self._active_call_task is not None:
                    self._active_call_task.cancel()
                    with suppress(BaseException):
                        await self._active_call_task
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    # force_close cancelled the source actor itself. Preserve
                    # the cancellation so transport teardown cannot be
                    # translated into a normal per-call failure and ignored.
                    raise
                raise MCPCallCancelledError(
                    f"MCP call {command.call_id!r} was cancelled"
                ) from error
            except TimeoutError as error:
                if self._active_call_task is not None:
                    self._active_call_task.cancel()
                    with suppress(BaseException):
                        await self._active_call_task
                raise MCPCallTimeoutError(
                    f"MCP call {command.call_id!r} timed out"
                ) from error

            result = _normalize_result(
                self.source,
                tool=tool,
                call_id=command.call_id,
                raw_result=raw_result,
                duration_ms=(time.perf_counter() - started) * 1_000,
                catalog_digest=self._catalog.catalog_digest,
                redaction_terms=self._redaction_terms,
            )
            if not command.response.done():
                command.response.set_result(result)
        except asyncio.CancelledError:
            raise
        except MCPClientError as error:
            if not command.response.done():
                command.response.set_exception(error)
        except BaseException as error:
            connection_error = MCPConnectionError(
                f"MCP source {self.source.source_id!r} tool call failed"
            )
            if not command.response.done():
                command.response.set_exception(connection_error)
            raise connection_error from error
        finally:
            self._cancelled_call_keys.discard(call_key)
            self._terminal_call_keys.pop(call_key, None)
            self._terminal_call_keys[call_key] = None
            if len(self._terminal_call_keys) > 1_024:
                evict_count = len(self._terminal_call_keys) - 512
                for terminal_key in tuple(self._terminal_call_keys)[:evict_count]:
                    self._terminal_call_keys.pop(terminal_key, None)
            self._active_call_key = None
            self._active_call_task = None

    async def _load_catalog(
        self,
        session: ClientSession,
    ) -> MCPToolCatalog:
        tools: list[MCPToolDefinition] = []
        catalog_bytes = 0
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(_MAX_CATALOG_PAGES):
            page = await asyncio.wait_for(
                session.list_tools(cursor=cursor),
                timeout=self.source.request_timeout_seconds,
            )
            for raw_tool in page.tools:
                try:
                    tool, definition_bytes = _tool_definition(
                        self.source.source_id,
                        raw_tool,
                        redaction_terms=self._redaction_terms,
                    )
                except _MCPResultBudgetExceeded as error:
                    raise MCPConnectionError(
                        f"MCP source {self.source.source_id!r} exceeded the bounded tool definition"
                    ) from error
                catalog_bytes += definition_bytes
                if catalog_bytes > _MAX_CATALOG_BYTES:
                    raise MCPConnectionError(
                        f"MCP source {self.source.source_id!r} exceeded the bounded catalog bytes"
                    )
                tools.append(tool)
            if len(tools) > _MAX_CATALOG_TOOLS:
                raise MCPConnectionError(
                    f"MCP source {self.source.source_id!r} exceeded the bounded tool catalog"
                )
            cursor = page.nextCursor
            if not cursor:
                break
            if cursor in seen_cursors:
                raise MCPConnectionError(
                    f"MCP source {self.source.source_id!r} repeated a catalog cursor"
                )
            seen_cursors.add(cursor)
        else:
            raise MCPConnectionError(
                f"MCP source {self.source.source_id!r} exceeded the bounded catalog page count"
            )
        tools.sort(key=lambda tool: tool.canonical_name)
        digest = _digest_json(
            [
                {
                    "canonical_name": tool.canonical_name,
                    "schema_digest": tool.schema_digest,
                }
                for tool in tools
            ]
        )
        changed = bool(self._catalog.tools and digest != self._catalog.catalog_digest)
        self._catalog_changed_since_initialize = (
            self._catalog_changed_since_initialize or changed
        )
        self._catalog_stale = False
        return MCPToolCatalog(
            source_id=self.source.source_id,
            tools=tuple(tools),
            catalog_digest=digest,
            changed_since_initialize=self._catalog_changed_since_initialize,
        )

    def _resolve_tool(self, name: str) -> MCPToolDefinition:
        matches = [
            tool
            for tool in self._catalog.tools
            if name in {tool.name, tool.canonical_name}
        ]
        if len(matches) != 1:
            raise MCPToolNotFoundError(
                f"MCP tool {name!r} was not found in source {self.source.source_id!r}"
            )
        return matches[0]

    async def _handle_message(self, message: Any) -> None:
        if isinstance(message, mcp_types.ToolListChangedNotification):
            self._catalog_stale = True

    def _fail_pending_commands(self, error: BaseException) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except asyncio.QueueEmpty:
                return
            if isinstance(command, _CallCommand):
                call_key = (
                    command.owner.key,
                    command.run_id,
                    command.call_id,
                )
                self._queued_call_keys.discard(call_key)
                self._terminal_call_keys.pop(call_key, None)
                self._terminal_call_keys[call_key] = None
            if not command.response.done():
                command.response.set_exception(error)


def _has_source_lease(
    leases: Iterable[tuple[str, object]],
    source_id: str,
) -> bool:
    for leased_source_id, _owner_key in leases:
        if leased_source_id == source_id:
            return True
    return False


class MCPClientManager:
    """Own live MCP source lifecycle behind a small async interface."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        latency_clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._environment = dict(os.environ if environment is None else environment)
        raw_initial_credential_keys = self._environment.get(
            MCP_CREDENTIAL_KEYS_ENV,
            "",
        )
        self._initial_credential_keys = frozenset(
            bounded_mcp_credential_environment_key_union(
                tuple(
                    key
                    for key in raw_initial_credential_keys.split(",")
                    if key
                )
            )
        )
        self._monotonic_clock = monotonic_clock
        self._latency_clock = latency_clock
        self._actors: dict[str, _MCPSourceActor] = {}
        self._sources: dict[str, MCPSourceDefinition] = {}
        self._configuration_digests: dict[str, str] = {}
        self._catalog_digests: dict[str, str] = {}
        self._leases: dict[
            tuple[str, tuple[str, str, str]],
            _MCPSourceLease,
        ] = {}
        self._initialize_metrics = _MutableMCPOperationMetrics()
        self._list_tools_metrics = _MutableMCPOperationMetrics()
        self._call_tool_metrics = _MutableMCPOperationMetrics()
        self._cancel_propagation_metrics = _MutableMCPOperationMetrics()
        self._reconnect_count = 0
        self._schema_change_count = 0
        self._metrics_lock = threading.Lock()
        self._lock = asyncio.Lock()
        self._source_locks: dict[str, asyncio.Lock] = {}
        self._lease_sweeper_task: asyncio.Task[None] | None = None
        self._lease_changed: asyncio.Event | None = None

    async def initialize(
        self,
        source: MCPSourceDefinition,
        owner: MCPOwnerIdentity,
        *,
        lease_ttl_seconds: float = _DEFAULT_SOURCE_LEASE_SECONDS,
    ) -> MCPServerCapabilities:
        return await self._measure_operation(
            self._initialize_metrics,
            lambda: self._initialize(
                source,
                owner,
                lease_ttl_seconds=lease_ttl_seconds,
            ),
        )

    async def _initialize(
        self,
        source: MCPSourceDefinition,
        owner: MCPOwnerIdentity,
        *,
        lease_ttl_seconds: float = _DEFAULT_SOURCE_LEASE_SECONDS,
    ) -> MCPServerCapabilities:
        added_credential_keys = (
            _source_credential_environment_keys(source)
            - self._initial_credential_keys
        )
        if added_credential_keys:
            raise MCPSourceConfigurationError(
                "MCP credential references changed after worker launch; restart Melix"
            )
        lease_ttl_seconds = _validated_lease_ttl(lease_ttl_seconds)
        self._ensure_lease_sweeper()
        async with self._source_lock(source.source_id):
            return await self._initialize_source_locked(
                source,
                owner,
                lease_ttl_seconds=lease_ttl_seconds,
            )

    async def _initialize_source_locked(
        self,
        source: MCPSourceDefinition,
        owner: MCPOwnerIdentity,
        *,
        lease_ttl_seconds: float,
    ) -> MCPServerCapabilities:
        await self._expire_source_leases_locked(source.source_id)
        async with self._lock:
            existing = self._actors.get(source.source_id)
            registered_source = self._sources.get(source.source_id)
            configuration_matches = (
                (existing is not None and existing.source == source)
                or (existing is None and registered_source == source)
            )
            source_lease_keys = [
                key for key in self._leases if key[0] == source.source_id
            ]
        if (
            not configuration_matches
            and any(key[1] != owner.key for key in source_lease_keys)
        ):
            raise MCPSourceOwnershipError(
                "MCP source configuration conflicts with another owner lease"
            )
        if existing is not None:
            if configuration_matches and existing.is_live:
                capabilities = await existing.start()
                async with self._lock:
                    if self._actors.get(source.source_id) is not existing:
                        raise MCPConnectionError(
                            f"MCP source {source.source_id!r} closed during initialization"
                        )
                    self._leases[(source.source_id, owner.key)] = _MCPSourceLease(
                        owner=owner,
                        configuration_digest=source.configuration_digest,
                        expires_at_monotonic=(
                            self._monotonic_clock() + lease_ttl_seconds
                        ),
                    )
                    self._observe_catalog_digest(
                        source.source_id,
                        capabilities.catalog_digest,
                    )
                self._signal_lease_change()
                return capabilities
            async with self._lock:
                if self._actors.get(source.source_id) is existing:
                    self._actors.pop(source.source_id, None)
                if not configuration_matches:
                    for key in source_lease_keys:
                        self._leases.pop(key, None)
                    self._sources.pop(source.source_id, None)
                    self._configuration_digests.pop(source.source_id, None)
                    self._catalog_digests.pop(source.source_id, None)
            await existing.force_close()
        elif not configuration_matches and (
            registered_source is not None or source_lease_keys
        ):
            async with self._lock:
                for key in source_lease_keys:
                    self._leases.pop(key, None)
                self._sources.pop(source.source_id, None)
                self._configuration_digests.pop(source.source_id, None)
                self._catalog_digests.pop(source.source_id, None)

        actor = _MCPSourceActor(source, environment=self._environment)
        async with self._lock:
            self._actors[source.source_id] = actor
            self._sources[source.source_id] = source
            self._configuration_digests[source.source_id] = (
                source.configuration_digest
            )
        try:
            capabilities = await actor.start()
        except BaseException as startup_error:
            # `start()` shields the actor's readiness future so cancelling the
            # initializing caller does not implicitly tear down the transport.
            # Cleanup happens outside the manager lock so another source can
            # continue cancellation and lease work independently.
            try:
                await actor.force_close()
            except BaseException as cleanup_error:
                if hasattr(startup_error, "add_note"):
                    startup_error.add_note(
                        "MCP source cleanup after failed initialization "
                        f"also failed: {cleanup_error!r}"
                    )
            async with self._lock:
                if self._actors.get(source.source_id) is actor:
                    self._actors.pop(source.source_id, None)
                    self._sources.pop(source.source_id, None)
                    self._configuration_digests.pop(source.source_id, None)
                    self._catalog_digests.pop(source.source_id, None)
                for key in tuple(self._leases):
                    if key[0] == source.source_id:
                        self._leases.pop(key, None)
            raise

        actor_was_replaced = False
        async with self._lock:
            if self._actors.get(source.source_id) is not actor:
                actor_was_replaced = True
            else:
                self._leases[(source.source_id, owner.key)] = _MCPSourceLease(
                    owner=owner,
                    configuration_digest=source.configuration_digest,
                    expires_at_monotonic=(
                        self._monotonic_clock() + lease_ttl_seconds
                    ),
                )
                self._observe_catalog_digest(
                    source.source_id,
                    capabilities.catalog_digest,
                )
        if actor_was_replaced:
            await actor.force_close()
            raise MCPConnectionError(
                f"MCP source {source.source_id!r} closed during initialization"
            )
        self._signal_lease_change()
        return capabilities

    async def list_tools(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
        *,
        refresh: bool = False,
    ) -> MCPToolCatalog:
        return await self._measure_operation(
            self._list_tools_metrics,
            lambda: self._list_tools(
                source_id,
                owner,
                refresh=refresh,
            ),
        )

    async def _list_tools(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
        *,
        refresh: bool,
    ) -> MCPToolCatalog:
        catalog = await (await self._leased_actor(source_id, owner)).list_tools(
            refresh=refresh
        )
        self._observe_catalog_digest(source_id, catalog.catalog_digest)
        return catalog

    async def call_tool(
        self,
        source_id: str,
        *,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        expected_schema_digest: str = "",
    ) -> MCPToolResult:
        return await self._measure_operation(
            self._call_tool_metrics,
            lambda: self._call_tool(
                source_id,
                owner=owner,
                run_id=run_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                expected_schema_digest=expected_schema_digest,
            ),
        )

    async def _call_tool(
        self,
        source_id: str,
        *,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        expected_schema_digest: str,
    ) -> MCPToolResult:
        if not run_id.strip():
            raise MCPSourceConfigurationError("MCP run_id must not be blank")
        if not call_id.strip():
            raise MCPSourceConfigurationError("MCP call_id must not be blank")
        try:
            return await (await self._leased_actor(source_id, owner)).call_tool(
                owner=owner,
                run_id=run_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                expected_schema_digest=expected_schema_digest,
            )
        except MCPToolSchemaChangedError:
            with self._metrics_lock:
                self._schema_change_count += 1
            raise

    async def cancel(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
    ) -> MCPCancellationReceipt:
        started = self._latency_clock()
        receipt = await self._cancel(source_id, owner, run_id, call_id)
        if receipt.propagation_acknowledged:
            with self._metrics_lock:
                self._cancel_propagation_metrics.record(
                    (self._latency_clock() - started) * 1_000,
                    failed=False,
                )
        return receipt

    async def _cancel(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
        run_id: str,
        call_id: str,
    ) -> MCPCancellationReceipt:
        actor = await self._leased_actor(source_id, owner)
        return await actor.cancel(owner, run_id, call_id)

    async def release(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
    ) -> bool:
        actor_to_close: _MCPSourceActor | None = None
        async with self._source_lock(source_id):
            async with self._lock:
                lease = self._leases.pop((source_id, owner.key), None)
                if lease is None:
                    return False
                actor = self._actors.get(source_id)
            self._signal_lease_change()
            if actor is not None:
                await actor.cancel_owner(owner)
            async with self._lock:
                if not _has_source_lease(self._leases, source_id):
                    actor_to_close = self._actors.pop(source_id, None)
                    self._sources.pop(source_id, None)
                    self._configuration_digests.pop(source_id, None)
                    self._catalog_digests.pop(source_id, None)
            if actor_to_close is not None:
                await actor_to_close.force_close()
        return True

    async def release_owner(self, owner: MCPOwnerIdentity) -> tuple[str, ...]:
        async with self._lock:
            source_ids = sorted(
                source_id
                for source_id, owner_key in self._leases
                if owner_key == owner.key
            )
        released = []
        for source_id in source_ids:
            if await self.release(source_id, owner):
                released.append(source_id)
        return tuple(released)

    async def close(self, source_id: str) -> None:
        async with self._source_lock(source_id):
            async with self._lock:
                actor = self._actors.pop(source_id, None)
                self._sources.pop(source_id, None)
                self._configuration_digests.pop(source_id, None)
                self._catalog_digests.pop(source_id, None)
                for key in tuple(self._leases):
                    if key[0] == source_id:
                        self._leases.pop(key, None)
            self._signal_lease_change()
            if actor is not None:
                await actor.force_close()

    async def close_all(self) -> None:
        sweeper = self._lease_sweeper_task
        self._lease_sweeper_task = None
        if sweeper is not None and sweeper is not asyncio.current_task():
            sweeper.cancel()
        async with self._lock:
            actors = list(self._actors.values())
            self._actors.clear()
            self._sources.clear()
            self._configuration_digests.clear()
            self._catalog_digests.clear()
            self._leases.clear()
            self._signal_lease_change()
        if sweeper is not None and sweeper is not asyncio.current_task():
            with suppress(asyncio.CancelledError):
                await sweeper
        results = await asyncio.gather(
            *(actor.force_close() for actor in actors),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    def metrics_snapshot(self) -> MCPClientMetricsSnapshot:
        with self._metrics_lock:
            return MCPClientMetricsSnapshot(
                schema_version="melix.mcp_client_metrics.v1",
                initialize=self._initialize_metrics.snapshot(),
                list_tools=self._list_tools_metrics.snapshot(),
                call_tool=self._call_tool_metrics.snapshot(),
                cancel_propagation=(
                    self._cancel_propagation_metrics.snapshot()
                ),
                reconnect_count=self._reconnect_count,
                schema_change_count=self._schema_change_count,
            )

    async def _measure_operation(
        self,
        metrics: _MutableMCPOperationMetrics,
        operation: Callable[[], Any],
    ) -> Any:
        started = self._latency_clock()
        failed = True
        try:
            result = await operation()
            failed = False
            return result
        finally:
            with self._metrics_lock:
                metrics.record(
                    (self._latency_clock() - started) * 1_000,
                    failed=failed,
                )

    def _observe_catalog_digest(self, source_id: str, digest: str) -> None:
        previous = self._catalog_digests.get(source_id)
        if previous is not None and previous != digest:
            with self._metrics_lock:
                self._schema_change_count += 1
        self._catalog_digests[source_id] = digest

    async def _leased_actor(
        self,
        source_id: str,
        owner: MCPOwnerIdentity,
    ) -> _MCPSourceActor:
        async with self._source_lock(source_id):
            await self._expire_source_leases_locked(source_id)
            async with self._lock:
                lease = self._leases.get((source_id, owner.key))
                if lease is None:
                    raise MCPSourceOwnershipError(
                        f"MCP source {source_id!r} is not leased to this owner"
                    )
                actor = self._actors.get(source_id)
                source = self._sources.get(source_id)
                remaining_seconds = max(
                    0.001,
                    lease.expires_at_monotonic - self._monotonic_clock(),
                )
                if actor is not None and actor.is_live:
                    return actor
            if source is None:
                raise MCPSourceNotInitializedError(
                    f"MCP source {source_id!r} is not initialized"
                )
            with self._metrics_lock:
                self._reconnect_count += 1
            await self._measure_operation(
                self._initialize_metrics,
                lambda: self._initialize_source_locked(
                    source,
                    owner,
                    lease_ttl_seconds=remaining_seconds,
                ),
            )
            async with self._lock:
                actor = self._actors.get(source_id)
            if actor is None:
                raise MCPSourceNotInitializedError(
                    f"MCP source {source_id!r} is not initialized"
                )
            return actor

    def _source_lock(self, source_id: str) -> asyncio.Lock:
        lock = self._source_locks.get(source_id)
        if lock is None:
            lock = asyncio.Lock()
            self._source_locks[source_id] = lock
        return lock

    async def _expire_source_leases(self, source_id: str) -> None:
        async with self._source_lock(source_id):
            await self._expire_source_leases_locked(source_id)

    async def _expire_source_leases_locked(self, source_id: str) -> None:
        now = self._monotonic_clock()
        async with self._lock:
            expired = [
                (key, lease)
                for key, lease in self._leases.items()
                if key[0] == source_id
                and lease.expires_at_monotonic <= now
            ]
            if not expired:
                return
            for key, _ in expired:
                self._leases.pop(key, None)
            actor = self._actors.get(source_id)
            actor_to_close = None
            if not _has_source_lease(self._leases, source_id):
                actor_to_close = self._actors.pop(source_id, None)
                self._sources.pop(source_id, None)
                self._configuration_digests.pop(source_id, None)
                self._catalog_digests.pop(source_id, None)
        self._signal_lease_change()
        if actor is not None:
            for _, lease in expired:
                await actor.cancel_owner(lease.owner)
        if actor_to_close is not None:
            await actor_to_close.force_close()

    def _ensure_lease_sweeper(self) -> None:
        if (
            self._lease_sweeper_task is not None
            and not self._lease_sweeper_task.done()
        ):
            return
        self._lease_changed = asyncio.Event()
        self._lease_sweeper_task = asyncio.create_task(
            self._sweep_expired_leases(),
            name="melix-mcp-lease-sweeper",
        )

    def _signal_lease_change(self) -> None:
        if self._lease_changed is not None:
            self._lease_changed.set()

    async def _sweep_expired_leases(self) -> None:
        while True:
            async with self._lock:
                now = self._monotonic_clock()
                expired_source_ids = tuple(
                    sorted(
                        {
                            source_id
                            for (source_id, _), lease in self._leases.items()
                            if lease.expires_at_monotonic <= now
                        }
                    )
                )
                next_expiry = min(
                    (
                        lease.expires_at_monotonic
                        for lease in self._leases.values()
                    ),
                    default=None,
                )
                wakeup = self._lease_changed
                assert wakeup is not None
                wakeup.clear()
            if expired_source_ids:
                await asyncio.gather(
                    *(
                        self._expire_source_leases(source_id)
                        for source_id in expired_source_ids
                    )
                )
                continue
            if next_expiry is None:
                await wakeup.wait()
                continue
            remaining = max(
                0.0,
                next_expiry - self._monotonic_clock(),
            )
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=remaining)
            except TimeoutError:
                pass


class _BoundedJSONLineBuffer:
    def __init__(
        self,
        *,
        source_id: str,
        max_message_bytes: int,
    ) -> None:
        self._source_id = source_id
        self._max_message_bytes = max_message_bytes
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        lines: list[bytes] = []
        start = 0
        while start < len(chunk):
            newline = chunk.find(b"\n", start)
            end = len(chunk) if newline < 0 else newline
            segment_size = end - start
            if len(self._buffer) + segment_size > self._max_message_bytes:
                raise _wire_limit_error(
                    self._source_id,
                    "stdio frame",
                    self._max_message_bytes,
                )
            self._buffer.extend(memoryview(chunk)[start:end])
            if newline < 0:
                break
            lines.append(bytes(self._buffer))
            self._buffer.clear()
            start = newline + 1
        return tuple(lines)


class _SSEEventByteBudget:
    def __init__(
        self,
        *,
        source_id: str,
        max_message_bytes: int,
    ) -> None:
        self._source_id = source_id
        self._max_message_bytes = max_message_bytes
        self._event_bytes = 0
        self._line_is_empty = True
        self._pending_cr = False
        self._dispatched_on_cr = False

    def observe(self, chunk: bytes) -> None:
        position = 0
        for match in _SSE_NEWLINE_BYTE_PATTERN.finditer(chunk):
            newline = match.start()
            byte = chunk[newline]
            if self._pending_cr:
                if newline == position and byte == 0x0A:
                    self._event_bytes += 1
                    if self._dispatched_on_cr:
                        self._event_bytes = 0
                    else:
                        self._check_budget()
                    self._pending_cr = False
                    self._dispatched_on_cr = False
                    position = newline + 1
                    continue
                self._pending_cr = False
                self._dispatched_on_cr = False

            if newline > position:
                self._event_bytes += newline - position
                self._line_is_empty = False
                self._check_budget()

            self._event_bytes += 1
            if byte == 0x0D:
                self._finish_line(ended_with_cr=True)
            else:
                self._finish_line(ended_with_cr=False)
            position = newline + 1

        if position < len(chunk):
            self._pending_cr = False
            self._dispatched_on_cr = False
            self._event_bytes += len(chunk) - position
            self._line_is_empty = False
            self._check_budget()

    def _finish_line(self, *, ended_with_cr: bool) -> None:
        self._check_budget()
        if self._line_is_empty:
            self._event_bytes = 0
            self._dispatched_on_cr = ended_with_cr
        self._line_is_empty = True
        self._pending_cr = ended_with_cr

    def _check_budget(self) -> None:
        if self._event_bytes > self._max_message_bytes:
            raise _wire_limit_error(
                self._source_id,
                "SSE event",
                self._max_message_bytes,
            )


class _WireLimitedHTTPResponseStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        *,
        source_id: str,
        max_message_bytes: int,
        is_sse: bool,
        report_failure: Callable[[MCPWireLimitError], None],
    ) -> None:
        self._stream = stream
        self._source_id = source_id
        self._max_message_bytes = max_message_bytes
        self._is_sse = is_sse
        self._report_failure = report_failure

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received_bytes = 0
        sse_budget = (
            _SSEEventByteBudget(
                source_id=self._source_id,
                max_message_bytes=self._max_message_bytes,
            )
            if self._is_sse
            else None
        )
        try:
            async for chunk in self._stream:
                if sse_budget is not None:
                    sse_budget.observe(chunk)
                else:
                    received_bytes += len(chunk)
                    if received_bytes > self._max_message_bytes:
                        raise _wire_limit_error(
                            self._source_id,
                            "HTTP response body",
                            self._max_message_bytes,
                        )
                yield chunk
        except MCPWireLimitError as error:
            self._report_failure(error)
            raise

    async def aclose(self) -> None:
        await self._stream.aclose()


async def _apply_http_wire_limits(
    response: httpx.Response,
    *,
    source_id: str,
    max_message_bytes: int,
    report_failure: Callable[[MCPWireLimitError], None],
) -> None:
    try:
        content_length = _validated_content_length(response.headers)
        if (
            content_length is not None
            and content_length > max_message_bytes
        ):
            raise _wire_limit_error(
                source_id,
                "HTTP Content-Length",
                max_message_bytes,
            )
        content_encoding = response.headers.get(
            "content-encoding",
            "identity",
        ).strip().lower()
        if content_encoding not in {"", "identity"}:
            raise MCPWireLimitError(
                f"MCP source {source_id!r} returned compressed HTTP "
                "content that cannot be bounded before decoding"
            )
    except MCPWireLimitError as error:
        report_failure(error)
        with suppress(BaseException):
            await response.aclose()
        raise

    content_type = response.headers.get("content-type", "")
    is_sse = (
        content_type.partition(";")[0].strip().lower()
        == "text/event-stream"
    )
    response.stream = _WireLimitedHTTPResponseStream(
        response.stream,
        source_id=source_id,
        max_message_bytes=max_message_bytes,
        is_sse=is_sse,
        report_failure=report_failure,
    )


@asynccontextmanager
async def _bounded_stdio_transport(
    server: StdioServerParameters,
    *,
    source_id: str,
    max_message_bytes: int,
):
    read_stream_writer, read_stream = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream[
        SessionMessage
    ](0)
    wire_failure = asyncio.get_running_loop().create_future()

    try:
        resolved_environment = get_default_environment()
        if server.env is not None:
            resolved_environment.update(server.env)
        # MCP stderr is untrusted and can echo credentials inherited through
        # environment_references. Never inherit the worker's stderr: that path
        # is persisted by the desktop runtime. The protocol already exposes
        # bounded typed connection failures, so child diagnostics are discarded
        # until a dedicated redacting, bounded sink is introduced.
        process = await _create_platform_compatible_process(
            command=_get_executable_command(server.command),
            args=server.args,
            env=resolved_environment,
            errlog=subprocess.DEVNULL,
            cwd=server.cwd,
        )
    except OSError:
        await read_stream.aclose()
        await write_stream.aclose()
        await read_stream_writer.aclose()
        await write_stream_reader.aclose()
        raise

    async def stdout_reader() -> None:
        assert process.stdout, "Opened process is missing stdout"
        line_buffer = _BoundedJSONLineBuffer(
            source_id=source_id,
            max_message_bytes=max_message_bytes,
        )
        async with read_stream_writer:
            try:
                while True:
                    try:
                        chunk = await process.stdout.receive()
                    except anyio.EndOfStream:
                        return
                    for line in line_buffer.feed(chunk):
                        try:
                            message = mcp_types.JSONRPCMessage.model_validate_json(
                                line
                            )
                        except Exception as error:
                            await read_stream_writer.send(error)
                            continue
                        await read_stream_writer.send(SessionMessage(message))
            except MCPWireLimitError as error:
                if not wire_failure.done():
                    wire_failure.set_result(error)
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()

    async def stdin_writer() -> None:
        assert process.stdin, "Opened process is missing stdin"
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    payload = session_message.message.model_dump_json(
                        by_alias=True,
                        exclude_none=True,
                    )
                    await process.stdin.send(
                        (payload + "\n").encode(
                            encoding=server.encoding,
                            errors=server.encoding_error_handler,
                        )
                    )
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as task_group, process:
        task_group.start_soon(stdout_reader)
        task_group.start_soon(stdin_writer)
        try:
            yield read_stream, write_stream, wire_failure
        finally:
            if process.stdin:
                with suppress(Exception):
                    await process.stdin.aclose()
            try:
                with anyio.fail_after(PROCESS_TERMINATION_TIMEOUT):
                    await process.wait()
            except TimeoutError:
                await _terminate_process_tree(process)
            except ProcessLookupError:
                pass
            await read_stream.aclose()
            await write_stream.aclose()
            await read_stream_writer.aclose()
            await write_stream_reader.aclose()


@asynccontextmanager
async def _streamable_http_transport(
    url: str,
    *,
    source_id: str,
    headers: Mapping[str, str],
    timeout: float,
    max_message_bytes: int,
):
    client_timeout = httpx.Timeout(
        timeout=timeout,
        connect=timeout,
        read=timeout,
        write=timeout,
        pool=timeout,
    )
    wire_failure = asyncio.get_running_loop().create_future()

    def report_failure(error: MCPWireLimitError) -> None:
        if not wire_failure.done():
            wire_failure.set_result(error)

    async def enforce_response_limit(response: httpx.Response) -> None:
        await _apply_http_wire_limits(
            response,
            source_id=source_id,
            max_message_bytes=max_message_bytes,
            report_failure=report_failure,
        )

    client_headers = httpx.Headers(headers)
    # A compressed response could expand beyond the raw-byte limit inside
    # httpx before the MCP parser sees it. Require identity transfer instead.
    client_headers["Accept-Encoding"] = "identity"
    async with httpx.AsyncClient(
        headers=client_headers,
        timeout=client_timeout,
        # A response hook is the earliest public httpx seam after headers and
        # preserves the default proxy, TLS trust, and connection-pool behavior.
        event_hooks={"response": [enforce_response_limit]},
        # Credential-bearing custom headers must never be replayed to a
        # redirect target. Operators configure the final MCP endpoint.
        follow_redirects=False,
    ) as client:
        async with streamable_http_client(
            url,
            http_client=client,
        ) as streams:
            yield (
                streams[0],
                streams[1],
                wire_failure,
            )


def _validated_content_length(headers: httpx.Headers) -> int | None:
    values = [
        token.strip()
        for value in headers.get_list("content-length")
        for token in value.split(",")
    ]
    if not values:
        return None
    if any(
        not value or not value.isascii() or not value.isdigit()
        for value in values
    ):
        raise MCPWireLimitError("MCP HTTP response has invalid Content-Length")
    if len(set(values)) != 1:
        raise MCPWireLimitError(
            "MCP HTTP response has conflicting Content-Length values"
        )
    value = values[0]
    if len(value) > 20:
        return 10**20
    return int(value)


def _wire_limit_error(
    source_id: str,
    boundary: str,
    max_message_bytes: int,
) -> MCPWireLimitError:
    return MCPWireLimitError(
        f"MCP source {source_id!r} {boundary} exceeded "
        f"{max_message_bytes} bytes"
    )


async def _await_with_wire_failure(
    operation: Awaitable[Any],
    wire_failure: asyncio.Future[MCPWireLimitError],
) -> Any:
    operation_task = asyncio.ensure_future(operation)
    try:
        completed, _ = await asyncio.wait(
            {operation_task, wire_failure},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if wire_failure in completed:
            if operation_task in completed:
                with suppress(BaseException):
                    operation_task.result()
            raise wire_failure.result()
        return operation_task.result()
    finally:
        if not operation_task.done():
            operation_task.cancel()
            with suppress(BaseException):
                await operation_task


def _find_wire_limit_error(error: BaseException) -> MCPWireLimitError | None:
    pending = [error]
    seen: set[int] = set()
    while pending:
        candidate = pending.pop()
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        if isinstance(candidate, MCPWireLimitError):
            return candidate
        if isinstance(candidate, BaseExceptionGroup):
            pending.extend(candidate.exceptions)
        if candidate.__cause__ is not None:
            pending.append(candidate.__cause__)
        if candidate.__context__ is not None:
            pending.append(candidate.__context__)
    return None


def _tool_definition(
    source_id: str,
    tool: mcp_types.Tool,
    *,
    redaction_terms: tuple[str, ...] = (),
) -> tuple[MCPToolDefinition, int]:
    normalized, encoded = _BoundedMCPResultBuilder(
        max_bytes=_MAX_TOOL_DEFINITION_BYTES,
        redaction_terms=redaction_terms,
        reject_redaction_terms=True,
    ).build(tool)
    if not isinstance(normalized, Mapping):
        raise _MCPResultBudgetExceeded("invalid_tool_definition", len(encoded))
    name = normalized.get("name")
    title = normalized.get("title", "")
    description = normalized.get("description", "")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(title, str)
        or not isinstance(description, str)
    ):
        raise _MCPResultBudgetExceeded("invalid_tool_definition", len(encoded))
    input_schema = _json_mapping(normalized.get("inputSchema"))
    output_schema = (
        _json_mapping(normalized.get("outputSchema"))
        if normalized.get("outputSchema") is not None
        else None
    )
    raw_annotations = normalized.get("annotations", {})
    annotations = _json_mapping(raw_annotations)
    schema_digest = _digest_json(
        {
            "name": name,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "annotations": annotations,
        }
    )
    return (
        MCPToolDefinition(
            source_id=source_id,
            name=name,
            canonical_name=_canonical_tool_name(source_id, name),
            title=title.strip(),
            description=description.strip(),
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
            schema_digest=schema_digest,
        ),
        len(encoded),
    )


def _server_capabilities(
    source: MCPSourceDefinition,
    initialized: mcp_types.InitializeResult,
    catalog: MCPToolCatalog,
    *,
    redaction_terms: tuple[str, ...] = (),
) -> MCPServerCapabilities:
    try:
        normalized, _ = _BoundedMCPResultBuilder(
            max_bytes=_MAX_SERVER_METADATA_BYTES,
            redaction_terms=redaction_terms,
            reject_redaction_terms=True,
        ).build(initialized)
        if not isinstance(normalized, Mapping):
            raise _MCPResultBudgetExceeded("invalid_server_metadata", 0)
        capabilities_payload = _json_mapping(normalized.get("capabilities"))
        server_info = _json_mapping(normalized.get("serverInfo"))
        protocol_version = normalized.get("protocolVersion")
        server_name = server_info.get("name")
        server_version = server_info.get("version")
        if (
            not isinstance(protocol_version, (str, int))
            or not isinstance(server_name, str)
            or not isinstance(server_version, str)
        ):
            raise _MCPResultBudgetExceeded("invalid_server_metadata", 0)
    except (_MCPResultBudgetExceeded, MCPClientError) as error:
        raise MCPConnectionError(
            f"MCP source {source.source_id!r} exceeded the bounded server metadata"
        ) from error
    capability_names = tuple(
        sorted(
            key
            for key, value in capabilities_payload.items()
            if value not in (None, False, {}, [])
        )
    )
    return MCPServerCapabilities(
        source_id=source.source_id,
        transport_kind=source.transport_kind,
        protocol_version=str(protocol_version),
        server_name=server_name,
        server_version=server_version,
        capability_names=capability_names,
        tool_count=len(catalog.tools),
        catalog_digest=catalog.catalog_digest,
        connected_at_unix_ms=int(time.time() * 1_000),
    )


def _normalize_result(
    source: MCPSourceDefinition,
    *,
    tool: MCPToolDefinition,
    call_id: str,
    raw_result: mcp_types.CallToolResult,
    duration_ms: float,
    catalog_digest: str,
    redaction_terms: tuple[str, ...] | None = None,
) -> MCPToolResult:
    builder = _BoundedMCPResultBuilder(
        max_bytes=source.max_result_bytes,
        redaction_terms=(
            source.redaction_terms
            if redaction_terms is None
            else redaction_terms
        ),
    )
    try:
        payload, encoded = builder.build(
            {
                "content": raw_result.content,
                "structured_content": raw_result.structuredContent,
                "is_error": bool(raw_result.isError),
            }
        )
        if not isinstance(payload, dict):
            raise _MCPResultBudgetExceeded(
                "invalid_result_shape",
                builder.observed_bytes,
            )
        content = payload.get("content")
        structured_content = payload.get("structured_content")
        if (
            not isinstance(content, list)
            or any(not isinstance(item, dict) for item in content)
            or (
                structured_content is not None
                and not isinstance(structured_content, dict)
            )
        ):
            raise _MCPResultBudgetExceeded(
                "invalid_result_shape",
                builder.observed_bytes,
            )
        original_bytes = len(encoded)
        truncated = False
    except _MCPResultBudgetExceeded as error:
        original_bytes = max(error.observed_bytes, builder.observed_bytes)
        if error.reason == "maximum_bytes":
            original_bytes = max(original_bytes, source.max_result_bytes + 1)
        truncated = True
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "MCP tool result exceeded the configured byte limit "
                        "and was omitted."
                    ),
                }
            ],
            "structured_content": {
                "truncated": True,
                "original_bytes": original_bytes,
                "reason": error.reason,
            },
            "is_error": bool(raw_result.isError),
        }
        encoded = _canonical_json_bytes(payload)

    return MCPToolResult(
        source_id=source.source_id,
        tool_name=tool.name,
        call_id=call_id,
        content=tuple(payload["content"]),
        structured_content=payload["structured_content"],
        is_error=bool(payload["is_error"]),
        original_bytes=original_bytes,
        emitted_bytes=len(encoded),
        truncated=truncated,
        duration_ms=duration_ms,
        catalog_digest=catalog_digest,
    )


class _MCPResultBudgetExceeded(RuntimeError):
    def __init__(self, reason: str, observed_bytes: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.observed_bytes = observed_bytes


class _BoundedMCPResultBuilder:
    """Convert MCP result models without an unbounded model_dump/JSON copy."""

    def __init__(
        self,
        *,
        max_bytes: int,
        redaction_terms: tuple[str, ...],
        reject_redaction_terms: bool = False,
    ) -> None:
        self._max_bytes = max_bytes
        self._redaction_terms = tuple(
            sorted(
                {term for term in redaction_terms if term},
                key=lambda term: (-len(term), term),
            )
        )
        self._reject_redaction_terms = reject_redaction_terms
        self._node_count = 0
        self._observed_bytes = 0
        self._ancestors: set[int] = set()

    @property
    def observed_bytes(self) -> int:
        return self._observed_bytes

    def build(self, value: Any) -> tuple[Any, bytes]:
        normalized = self._convert(value, depth=0)
        encoded = _canonical_json_bytes(normalized)
        if len(encoded) > self._max_bytes:
            raise _MCPResultBudgetExceeded("maximum_bytes", len(encoded))
        return normalized, encoded

    def _convert(self, value: Any, *, depth: int) -> Any:
        # Account for the node before evaluating any limit. This append-before-
        # limit order prevents a boundary node or self-reference from escaping
        # the node/depth budget without being recorded.
        self._node_count += 1
        self._charge(1)
        container_id: int | None = None
        if isinstance(value, (Mapping, list, tuple)) or hasattr(
            value,
            "__pydantic_fields__",
        ):
            container_id = id(value)
            if container_id in self._ancestors:
                raise _MCPResultBudgetExceeded(
                    "cyclic_result",
                    self._observed_bytes,
                )
            self._ancestors.add(container_id)
        try:
            if self._node_count > _MAX_RESULT_NODES:
                raise _MCPResultBudgetExceeded(
                    "maximum_nodes",
                    self._observed_bytes,
                )
            if depth > _MAX_RESULT_DEPTH:
                raise _MCPResultBudgetExceeded(
                    "maximum_depth",
                    self._observed_bytes,
                )
            if hasattr(value, "__pydantic_fields__"):
                return self._convert_pydantic_model(value, depth=depth)
            if isinstance(value, Mapping):
                converted: dict[str, Any] = {}
                for raw_key, raw_item in value.items():
                    if not isinstance(raw_key, str):
                        raise _MCPResultBudgetExceeded(
                            "non_string_key",
                            self._observed_bytes,
                        )
                    key = self._redact_text(raw_key)
                    self._charge(len(_canonical_json_bytes(key)) + 1)
                    converted[key] = self._convert(
                        raw_item,
                        depth=depth + 1,
                    )
                return converted
            if isinstance(value, (list, tuple)):
                converted_items: list[Any] = []
                for item in value:
                    converted_items.append(
                        self._convert(item, depth=depth + 1)
                    )
                    self._charge(1)
                return converted_items
            if isinstance(value, str):
                self._reject_unbounded_text(value)
                converted_text = self._redact_text(value)
                self._charge(len(_canonical_json_bytes(converted_text)))
                return converted_text
            if isinstance(value, float) and not math.isfinite(value):
                raise _MCPResultBudgetExceeded(
                    "non_finite_number",
                    self._observed_bytes,
                )
            if value is None or isinstance(value, (bool, int, float)):
                self._charge(len(_canonical_json_bytes(value)))
                return value
            if isinstance(value, (bytes, bytearray, memoryview)):
                byte_count = len(value)
                self._charge(byte_count)
                return {
                    "binary_omitted": True,
                    "byte_count": byte_count,
                }
            raise _MCPResultBudgetExceeded(
                "unsupported_result_type",
                self._observed_bytes,
            )
        finally:
            if container_id is not None:
                self._ancestors.discard(container_id)

    def _convert_pydantic_model(self, value: Any, *, depth: int) -> dict[str, Any]:
        fields = getattr(value, "__pydantic_fields__", {})
        converted: dict[str, Any] = {}
        for field_name, field_info in fields.items():
            field_value = getattr(value, field_name)
            if field_value is None:
                continue
            alias = (
                getattr(field_info, "serialization_alias", None)
                or getattr(field_info, "alias", None)
                or field_name
            )
            key = self._redact_text(str(alias))
            self._charge(len(_canonical_json_bytes(key)) + 1)
            converted[key] = self._convert(
                field_value,
                depth=depth + 1,
            )
        extras = getattr(value, "__pydantic_extra__", None)
        if extras:
            for raw_key, raw_item in extras.items():
                key = self._redact_text(str(raw_key))
                self._charge(len(_canonical_json_bytes(key)) + 1)
                converted[key] = self._convert(
                    raw_item,
                    depth=depth + 1,
                )
        return converted

    def _redact_text(self, value: str) -> str:
        self._reject_unbounded_text(value)
        if self._reject_redaction_terms and any(
            term in value for term in self._redaction_terms
        ):
            raise _MCPResultBudgetExceeded(
                "credential_echo",
                self._observed_bytes,
            )
        redacted = value
        for term in self._redaction_terms:
            replacement_growth = len("[REDACTED]") - len(term)
            if replacement_growth > 0:
                occurrence_count = redacted.count(term)
                if (
                    len(redacted) + occurrence_count * replacement_growth
                    > self._max_bytes
                ):
                    self._observed_bytes += self._max_bytes + 1
                    raise _MCPResultBudgetExceeded(
                        "maximum_bytes",
                        self._observed_bytes,
                    )
            redacted = redacted.replace(term, "[REDACTED]")
        return redacted

    def _reject_unbounded_text(self, value: str) -> None:
        if len(value) > self._max_bytes:
            self._observed_bytes += self._max_bytes + 1
            raise _MCPResultBudgetExceeded(
                "maximum_bytes",
                self._observed_bytes,
            )

    def _charge(self, byte_count: int) -> None:
        self._observed_bytes += byte_count
        if self._observed_bytes > self._max_bytes:
            raise _MCPResultBudgetExceeded(
                "maximum_bytes",
                self._observed_bytes,
            )


def _canonical_tool_name(source_id: str, tool_name: str) -> str:
    source_component = _CANONICAL_COMPONENT_PATTERN.sub("_", source_id).strip("_")
    tool_component = _CANONICAL_COMPONENT_PATTERN.sub("_", tool_name).strip("_")
    candidate = f"mcp__{source_component}__{tool_component}"
    if len(candidate) <= 64:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:10]
    return f"{candidate[:53]}_{digest}"


def _json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    encoded = _canonical_json_bytes(value)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise MCPClientError("MCP schema or structured content must be an object")
    return decoded


def _validated_lease_ttl(value: float) -> float:
    if not isinstance(value, (int, float)) or not (0 < value <= _MAX_SOURCE_LEASE_SECONDS):
        raise MCPSourceOwnershipError(
            "MCP source lease TTL must be greater than zero and no more than "
            f"{_MAX_SOURCE_LEASE_SECONDS:g} seconds"
        )
    return float(value)


def _resolved_redaction_terms(
    source: MCPSourceDefinition,
    environment: Mapping[str, str],
) -> tuple[str, ...]:
    terms = set(source.redaction_terms)
    transport = source.transport
    if isinstance(transport, MCPStdioTransport):
        resolved_credentials = transport.resolved_environment(environment)
        for value in resolved_credentials.values():
            terms.update(_credential_variants(value))
    else:
        resolved_headers = transport.resolved_headers(environment)
        for header in transport.header_environment_references:
            value = resolved_headers.get(header.strip())
            if value is not None:
                terms.update(_credential_variants(value))
        for header, value in transport.headers.items():
            if _CREDENTIAL_HEADER_PATTERN.search(header):
                terms.update(_credential_variants(value))
    return tuple(
        sorted(
            {term for term in terms if term},
            key=lambda term: (-len(term), term),
        )
    )


def _credential_variants(value: str) -> set[str]:
    variants = {value} if value else set()
    scheme, separator, credential = value.partition(" ")
    if (
        separator
        and credential
        and scheme.casefold() in {"bearer", "basic", "token"}
    ):
        variants.add(credential)
    return variants


def _redact(value: Any, terms: tuple[str, ...]) -> Any:
    active_terms = tuple(term for term in terms if term)
    if not active_terms:
        return value
    if isinstance(value, str):
        redacted = value
        for term in active_terms:
            redacted = redacted.replace(term, "[REDACTED]")
        return redacted
    if isinstance(value, list):
        return [_redact(item, active_terms) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item, active_terms) for item in value)
    if isinstance(value, dict):
        return {
            str(key): _redact(item, active_terms)
            for key, item in value.items()
        }
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _observe_future_exception(future: asyncio.Future[Any]) -> None:
    if not future.cancelled():
        future.exception()
