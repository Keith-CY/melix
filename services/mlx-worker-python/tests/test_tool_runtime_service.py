from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from concurrent import futures
from pathlib import Path

import grpc
import pytest

from packages.protocol.python.worker.v1 import common_pb2, tool_runtime_pb2
from worker.grpc_server import (
    BootstrapMetricsExporter,
    WorkerToolRuntimeService,
    _abort_rpc_deadline,
    _mcp_source_definition,
    _remaining_rpc_seconds,
)
from worker.runtime.mcp_client import (
    MCPClientMetricsSnapshot,
    MCPOperationMetricsSnapshot,
    MCPSourceConfigurationError,
    MCPStreamableHTTPTransport,
)
from worker.runtime.tool_execution_runtime import (
    ToolCancellationReceipt,
    ToolExecutionRuntimeMetricsSnapshot,
    ToolRunCancellationReceipt,
)


SERVER_SOURCE = """
from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP


server = FastMCP("Melix Worker Tool Service Fixture", log_level="ERROR")


@server.tool()
def add(a: int, b: int) -> dict[str, int]:
    \"\"\"Add two integers.\"\"\"
    return {"sum": a + b}


@server.tool()
async def delayed_write(path: str, delay_ms: int) -> dict[str, bool]:
    \"\"\"Write after a cancellable delay.\"\"\"
    await asyncio.sleep(delay_ms / 1000)
    Path(path).write_text("committed", encoding="utf-8")
    return {"committed": True}


server.run(transport="stdio")
"""


def _source(tmp_path: Path) -> tool_runtime_pb2.AgentToolSourceConfig:
    server_path = tmp_path / "worker_tool_service_server.py"
    server_path.write_text(SERVER_SOURCE, encoding="utf-8")
    return tool_runtime_pb2.AgentToolSourceConfig(
        source_id="worker-service-fixture",
        enabled=True,
        stdio=tool_runtime_pb2.MCPStdioTransport(
            command=sys.executable,
            arguments=[str(server_path)],
            working_directory=str(tmp_path),
        ),
        request_timeout_ms=5_000,
        connect_timeout_ms=30_000,
        max_result_bytes=262_144,
    )


def _list(service: WorkerToolRuntimeService, source):
    return service.ListAgentTools(
        tool_runtime_pb2.ListAgentToolsRequest(
            id=common_pb2.RequestIdentity(
                session_id="session",
                branch_id="branch",
            ),
            sources=[source],
            owner_actor_id="operator",
        ),
        None,
    )


def _tool(catalog, name: str):
    return next(
        tool for tool in catalog.tools if tool.source_tool_name == name
    )


def _execution_request(
    *,
    tool,
    call_id: str,
    arguments: dict[str, object],
    session_id: str = "session",
    branch_id: str = "branch",
    actor_id: str = "operator",
) -> tool_runtime_pb2.ExecuteAgentToolRequest:
    return tool_runtime_pb2.ExecuteAgentToolRequest(
        context=tool_runtime_pb2.AgentToolExecutionContext(
            run_id="service-run",
            session_id=session_id,
            branch_id=branch_id,
            actor_id=actor_id,
            admission_state="approved",
            approval_grant_digest="approval-digest",
            policy_revision="policy-v1",
        ),
        call_id=call_id,
        tool_name=tool.name,
        source_id=tool.source_id,
        arguments_json=json.dumps(arguments, sort_keys=True),
        expected_schema_digest=tool.schema_digest,
        idempotency_key=f"idempotency-{call_id}",
    )


class _DisconnectableContext:
    def __init__(self) -> None:
        self._callbacks = []
        self._active = True

    def add_callback(self, callback):
        if not self._active:
            return False
        self._callbacks.append(callback)
        return True

    def time_remaining(self):
        return None

    def disconnect(self) -> None:
        self._active = False
        for callback in tuple(self._callbacks):
            callback()


class _DeadlineContext:
    def __init__(self, remaining: float | None) -> None:
        self.remaining = remaining
        self.aborted = None

    def time_remaining(self):
        return self.remaining

    def abort(self, status, message):
        self.aborted = (status, message)


class _RejectingCallbackContext:
    def add_callback(self, callback):
        del callback
        return False

    def time_remaining(self):
        return None


class _CancellationFixtureRuntime:
    def __init__(self) -> None:
        self.execute_count = 0

    async def execute(self, call, context):
        del call, context
        self.execute_count += 1
        raise asyncio.CancelledError

    async def cancel(self, run_id, call_id, owner, cancellation_id=""):
        del run_id, call_id, owner, cancellation_id
        raise RuntimeError("fixture cancellation failure")

    async def close(self):
        return None


class _RunCleanupFixtureRuntime(_CancellationFixtureRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    async def cancel_run(
        self,
        run_id,
        owner,
        cancellation_id="",
    ):
        self.requests.append((run_id, owner, cancellation_id))
        return ToolRunCancellationReceipt(
            run_id=run_id,
            cancellation_id="worker-stable-cancellation",
            disposition="accepted",
            side_effect_state="unknown",
            calls=(
                ToolCancellationReceipt(
                    run_id=run_id,
                    call_id="active-call",
                    disposition="accepted",
                    adapter_kind="mcp",
                    source_id="source",
                    cancellation_id="worker-stable-call-cancellation",
                    side_effect_state="unknown",
                ),
            ),
            computer_use_disposition="already_terminal",
        )


def test_worker_tool_service_exports_typed_agent_runtime_metrics(
    tmp_path: Path,
) -> None:
    def operation(
        *,
        count: int,
        failures: int,
        total: float,
        last: float,
        maximum: float,
    ) -> MCPOperationMetricsSnapshot:
        return MCPOperationMetricsSnapshot(
            invocation_count=count,
            failure_count=failures,
            total_latency_ms=total,
            last_latency_ms=last,
            maximum_latency_ms=maximum,
        )

    class MetricsRuntime:
        def __init__(self) -> None:
            zero = operation(
                count=0,
                failures=0,
                total=0.0,
                last=0.0,
                maximum=0.0,
            )
            self.snapshot = ToolExecutionRuntimeMetricsSnapshot(
                schema_version="melix.tool_execution_runtime_metrics.v1",
                mcp=MCPClientMetricsSnapshot(
                    schema_version="melix.mcp_client_metrics.v1",
                    initialize=zero,
                    list_tools=zero,
                    call_tool=zero,
                    cancel_propagation=zero,
                    reconnect_count=0,
                    schema_change_count=0,
                ),
                worker_to_adapter_cancel=zero,
            )

        async def cancel(self, run_id, call_id, owner, cancellation_id=""):
            del owner, cancellation_id
            self.snapshot = ToolExecutionRuntimeMetricsSnapshot(
                schema_version="melix.tool_execution_runtime_metrics.v1",
                mcp=MCPClientMetricsSnapshot(
                    schema_version="melix.mcp_client_metrics.v1",
                    initialize=operation(
                        count=1,
                        failures=0,
                        total=1.25,
                        last=1.25,
                        maximum=1.25,
                    ),
                    list_tools=operation(
                        count=2,
                        failures=1,
                        total=4.5,
                        last=2.75,
                        maximum=2.75,
                    ),
                    call_tool=operation(
                        count=3,
                        failures=0,
                        total=9.0,
                        last=3.5,
                        maximum=4.0,
                    ),
                    cancel_propagation=operation(
                        count=1,
                        failures=0,
                        total=0.125,
                        last=0.125,
                        maximum=0.125,
                    ),
                    reconnect_count=4,
                    schema_change_count=2,
                ),
                worker_to_adapter_cancel=operation(
                    count=1,
                    failures=0,
                    total=0.375,
                    last=0.375,
                    maximum=0.375,
                ),
            )
            return ToolCancellationReceipt(
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                adapter_kind="mcp",
                source_id="metrics-source",
                cancellation_id="stable-metrics-cancellation",
                side_effect_state="unknown",
            )

        def metrics_snapshot(self) -> ToolExecutionRuntimeMetricsSnapshot:
            return self.snapshot

        async def close(self) -> None:
            return None

    metrics_path = tmp_path / "worker-agent-metrics.json"
    runtime = MetricsRuntime()
    service = WorkerToolRuntimeService(
        runtime=runtime,
        metrics_exporter=BootstrapMetricsExporter(str(metrics_path)),
    )
    try:
        initial = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
        assert initial["agent.mcp.call_tool_ms.sample_count"] == 0

        response = service.CancelAgentTool(
            tool_runtime_pb2.CancelAgentToolRequest(
                run_id="metrics-run",
                call_id="metrics-call",
                session_id="session",
                branch_id="branch",
                actor_id="operator",
                cancellation_id="caller-cancellation",
            ),
            None,
        )
        assert response.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED
        )

        values = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
        assert values["agent.mcp.initialize_ms"] == 1.25
        assert values["agent.mcp.list_tools_ms.sample_count"] == 2
        assert values["agent.mcp.list_tools_ms.failure_count"] == 1
        assert values["agent.mcp.call_tool_ms.total_ms"] == 9.0
        assert values["agent.mcp.call_tool_ms.max_ms"] == 4.0
        assert values["agent.mcp.cancel_propagation_ms"] == 0.125
        assert values["agent.mcp.reconnect_count"] == 4
        assert values["agent.mcp.schema_change_count"] == 2
        assert values["agent.cancel.worker_to_adapter_ms"] == 0.375
        assert values[
            "agent.cancel.worker_to_adapter_ms.sample_count"
        ] == 1
    finally:
        service.close()


def _raw_execution_request(
    *,
    call_id: str,
    tool_name: str,
    arguments_json: str,
) -> tool_runtime_pb2.ExecuteAgentToolRequest:
    return tool_runtime_pb2.ExecuteAgentToolRequest(
        context=tool_runtime_pb2.AgentToolExecutionContext(
            run_id="service-run",
            session_id="session",
            branch_id="branch",
            actor_id="operator",
            admission_state="allow",
        ),
        call_id=call_id,
        tool_name=tool_name,
        source_id="builtin",
        arguments_json=arguments_json,
    )


def test_worker_tool_service_bounds_public_argument_errors() -> None:
    service = WorkerToolRuntimeService()
    try:
        malformed = list(
            service.ExecuteAgentTool(
                _raw_execution_request(
                    call_id="malformed-json",
                    tool_name="local_compute",
                    arguments_json="{",
                ),
                None,
            )
        )
        assert malformed[-1].error.message == (
            "Tool arguments must be a valid JSON object."
        )

        non_object = list(
            service.ExecuteAgentTool(
                _raw_execution_request(
                    call_id="non-object-json",
                    tool_name="local_compute",
                    arguments_json="[]",
                ),
                None,
            )
        )
        assert non_object[-1].error.code == "tool_execution_runtime_error"
        assert non_object[-1].error.message == "Tool execution failed."

        unavailable = list(
            service.ExecuteAgentTool(
                _raw_execution_request(
                    call_id="unknown-tool",
                    tool_name="not-a-tool",
                    arguments_json="{}",
                ),
                None,
            )
        )
        assert unavailable[-1].error.code == "tool_not_found"
        assert unavailable[-1].error.message == (
            "The requested tool is unavailable."
        )
    finally:
        service.close()


def test_worker_tool_service_projects_timeout_and_cancelled_future() -> None:
    runtime = _CancellationFixtureRuntime()
    timeout_service = WorkerToolRuntimeService(runtime=runtime)
    try:
        timeout_events = list(
            timeout_service.ExecuteAgentTool(
                _raw_execution_request(
                    call_id="deadline-call",
                    tool_name="fixture",
                    arguments_json="{}",
                ),
                _DeadlineContext(0.0),
            )
        )
        assert timeout_events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_TIMEOUT
        )

        cancelled_events = list(
            timeout_service.ExecuteAgentTool(
                _raw_execution_request(
                    call_id="cancelled-future",
                    tool_name="fixture",
                    arguments_json="{}",
                ),
                _RejectingCallbackContext(),
            )
        )
        assert [event.seq for event in cancelled_events] == [1, 2]
        time.sleep(0.05)
        assert runtime.execute_count == 0

        with pytest.raises(futures.CancelledError):
            timeout_service.CancelAgentTool(
                    tool_runtime_pb2.CancelAgentToolRequest(
                        run_id="service-run",
                        call_id="reject-callback",
                        cancellation_id="cancel-reject-callback",
                        session_id="session",
                    branch_id="branch",
                    actor_id="operator",
                ),
                _RejectingCallbackContext(),
            )
    finally:
        timeout_service.close()


def test_worker_tool_service_projects_owner_bound_run_cleanup() -> None:
    runtime = _RunCleanupFixtureRuntime()
    service = WorkerToolRuntimeService(runtime=runtime)
    try:
        response = service.CancelAgentRunTools(
            tool_runtime_pb2.CancelAgentRunToolsRequest(
                run_id="service-run",
                cancellation_id="control-plane-correlation",
                session_id="session",
                branch_id="branch",
                actor_id="operator",
            ),
            None,
        )
        assert response.run_id == "service-run"
        assert response.cancellation_id == "control-plane-correlation"
        assert response.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED
        )
        assert response.side_effect_state == (
            tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
        )
        assert response.computer_use_disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_ALREADY_TERMINAL
        )
        assert len(response.calls) == 1
        assert response.calls[0].call_id == "active-call"
        assert runtime.requests[0][0] == "service-run"
        assert runtime.requests[0][1].key == (
            "session",
            "branch",
            "operator",
        )
        assert runtime.requests[0][2] == "control-plane-correlation"
    finally:
        service.close()


def test_worker_tool_service_source_and_deadline_helpers() -> None:
    definition = _mcp_source_definition(
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="http-fixture",
            enabled=True,
            streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                url="http://127.0.0.1:8123/mcp",
                headers={"X-Fixture": "visible"},
                header_environment_references={"Authorization": "MCP_TOKEN"},
            ),
        )
    )
    assert isinstance(definition.transport, MCPStreamableHTTPTransport)
    assert definition.transport.headers == {"X-Fixture": "visible"}

    with pytest.raises(ValueError, match="transport is required"):
        _mcp_source_definition(
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id="missing-transport"
            )
        )

    for reserved_source in (
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="reserved-stdio",
            enabled=True,
            stdio=tool_runtime_pb2.MCPStdioTransport(
                command=sys.executable,
                environment_references={"TOKEN": "PATH"},
            ),
        ),
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="reserved-http",
            enabled=True,
            streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                header_environment_references={
                    "Authorization": "MELIX_GATEWAY_BEARER_TOKEN"
                },
            ),
        ),
    ):
        with pytest.raises(
            MCPSourceConfigurationError,
            match="reserved Melix process key",
        ):
            _mcp_source_definition(reserved_source)

    for unsafe_reference_source in (
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="oversized-child-key",
            enabled=True,
            stdio=tool_runtime_pb2.MCPStdioTransport(
                command=sys.executable,
                environment_references={"A" * 256: "SECRET"},
            ),
        ),
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="oversized-header-name",
            enabled=True,
            streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                header_environment_references={"X" * 256: "SECRET"},
            ),
        ),
        tool_runtime_pb2.AgentToolSourceConfig(
            source_id="invalid-static-header-name",
            enabled=True,
            streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers={"Bad:Header": "visible"},
            ),
        ),
    ):
        with pytest.raises(MCPSourceConfigurationError):
            _mcp_source_definition(unsafe_reference_source)

    context = _DeadlineContext(0.25)
    assert _remaining_rpc_seconds(0, context) == 0.25
    assert _remaining_rpc_seconds(
        0,
        _DeadlineContext(float("inf")),
    ) is None
    assert _remaining_rpc_seconds(
        0,
        _DeadlineContext(threading.TIMEOUT_MAX * 2),
    ) is None
    assert _remaining_rpc_seconds(
        0,
        _DeadlineContext("not-a-timeout"),
    ) is None
    explicit_deadline = int(time.time() * 1_000) + 1_000
    explicit_remaining = _remaining_rpc_seconds(
        explicit_deadline,
        _DeadlineContext(float("inf")),
    )
    assert explicit_remaining is not None
    assert 0 < explicit_remaining <= 1
    with pytest.raises(futures.TimeoutError, match="fixture deadline"):
        _abort_rpc_deadline(context, "fixture deadline")
    assert context.aborted is not None


def test_worker_tool_service_lists_and_executes_real_mcp_source(
    tmp_path: Path,
) -> None:
    melix_home = tmp_path / "melix-home"
    metrics_path = tmp_path / "python-worker-metrics.json"
    service = WorkerToolRuntimeService(
        environment={"MELIX_HOME": str(melix_home)},
        metrics_exporter=BootstrapMetricsExporter(str(metrics_path)),
    )
    try:
        catalog = _list(service, _source(tmp_path))
        assert catalog.live_source_count == 1
        assert catalog.sources[0].connection_state == "live"
        assert catalog.sources[0].server_name == (
            "Melix Worker Tool Service Fixture"
        )
        add = _tool(catalog, "add")

        events = list(
            service.ExecuteAgentTool(
                _execution_request(
                    tool=add,
                    call_id="service-add",
                    arguments={"a": 10, "b": 32},
                ),
                None,
            )
        )
        assert [event.seq for event in events] == [1, 2, 3]
        assert [event.phase for event in events] == [
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_QUEUED,
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_STARTED,
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_COMPLETED,
        ]
        observation = json.loads(events[-1].result.observation_json)
        assert observation["payload"]["structured_content"] == {"sum": 42}
        assert observation["untrusted_context_receipt_count"] >= 2
        evidence_reference = events[-1].result.evidence_reference
        assert evidence_reference.startswith("state/agent-tool-evidence/")
        assert (melix_home / evidence_reference).is_file()
        receipt = json.loads(events[-1].result.receipt_json)
        assert receipt["evidence_reference"] == evidence_reference
        assert receipt["evidence_persisted"] is True
        metric_values = json.loads(
            metrics_path.read_text(encoding="utf-8")
        )["values"]
        assert metric_values["agent.mcp.initialize_ms.sample_count"] == 1
        assert metric_values["agent.mcp.list_tools_ms.sample_count"] == 2
        assert metric_values["agent.mcp.call_tool_ms.sample_count"] == 1
        assert metric_values["agent.mcp.initialize_ms"] > 0
        assert metric_values["agent.mcp.call_tool_ms"] > 0
        assert metric_values["agent.mcp.reconnect_count"] == 0
        assert metric_values["agent.mcp.schema_change_count"] == 0

        invalid_events = list(
            service.ExecuteAgentTool(
                _execution_request(
                    tool=add,
                    call_id="service-invalid-schema",
                    arguments={"a": "invalid", "b": 2},
                ),
                None,
            )
        )
        assert invalid_events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED
        )
        assert invalid_events[-1].error.code == (
            "tool_arguments_schema_invalid"
        )
    finally:
        service.close()


def test_worker_tool_service_reconciles_disabled_and_removed_sources(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    try:
        source = _source(tmp_path)
        assert _list(service, source).live_source_count == 1

        source.enabled = False
        disabled = _list(service, source)
        assert disabled.live_source_count == 0
        assert disabled.sources[0].connection_state == "disabled"
        assert all(
            tool.source_id != "worker-service-fixture"
            for tool in disabled.tools
        )

        source.enabled = True
        assert _list(service, source).live_source_count == 1
        removed = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session",
                    branch_id="branch",
                ),
                owner_actor_id="operator",
                release_sources=True,
            ),
            None,
        )
        assert removed.live_source_count == 0
        assert all(
            tool.source_id != "worker-service-fixture"
            for tool in removed.tools
        )
    finally:
        service.close()


def test_worker_tool_service_rejects_duplicate_source_ids(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    try:
        first = _source(tmp_path)
        second = tool_runtime_pb2.AgentToolSourceConfig()
        second.CopyFrom(first)
        catalog = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session",
                    branch_id="branch",
                ),
                sources=[first, second],
                owner_actor_id="operator",
            ),
            None,
        )
        assert catalog.live_source_count == 0
        assert [receipt.error_code for receipt in catalog.sources] == [
            "mcp_source_id_duplicate",
            "mcp_source_id_duplicate",
        ]
    finally:
        service.close()


@pytest.mark.parametrize(
    "limit_kind",
    (
        "source-count",
        "reference-count",
        "mixed-http-header-count",
        "source-key-bytes",
        "target-name-bytes",
    ),
)
def test_worker_tool_service_rejects_catalog_wide_mcp_limit_bypass(
    limit_kind: str,
) -> None:
    if limit_kind == "source-count":
        sources = [
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id=f"source-{index}",
                enabled=False,
                stdio=tool_runtime_pb2.MCPStdioTransport(command="/usr/bin/true"),
            )
            for index in range(257)
        ]
    elif limit_kind == "reference-count":
        sources = [
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id=f"source-{index}",
                enabled=False,
                stdio=tool_runtime_pb2.MCPStdioTransport(
                    command="/usr/bin/true",
                    environment_references={
                        f"TOKEN_{index}_{offset}": "SHARED_SECRET"
                        for offset in range(5)
                    },
                ),
            )
            for index in range(205)
        ]
    elif limit_kind == "mixed-http-header-count":
        sources = [
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id=f"source-{index}",
                enabled=False,
                streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                    url="https://example.com/mcp",
                    headers={f"X-Static-{offset}": "visible" for offset in range(3)},
                    header_environment_references={
                        f"X-Secret-{offset}": "SHARED_SECRET"
                        for offset in range(3)
                    },
                ),
            )
            for index in range(171)
        ]
    elif limit_kind == "source-key-bytes":
        sources = [
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id=f"source-{index}",
                enabled=False,
                stdio=tool_runtime_pb2.MCPStdioTransport(
                    command="/usr/bin/true",
                    environment_references={
                        "TOKEN": f"SECRET_{index}_" + "A" * 240,
                    },
                ),
            )
            for index in range(132)
        ]
    else:
        sources = [
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id=f"source-{index}",
                enabled=False,
                stdio=tool_runtime_pb2.MCPStdioTransport(
                    command="/usr/bin/true",
                    environment_references={
                        f"TOKEN_{index}_" + "A" * 240: "SHARED_SECRET",
                    },
                ),
            )
            for index in range(132)
        ]

    service = WorkerToolRuntimeService()
    try:
        catalog = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session",
                    branch_id="branch",
                ),
                sources=sources,
                owner_actor_id="operator",
            ),
            None,
        )
        assert catalog.live_source_count == 0
        assert len(catalog.sources) == len(sources)
        assert {
            receipt.error_code for receipt in catalog.sources
        } == {"mcp_source_catalog_limit_exceeded"}
    finally:
        service.close()


def test_worker_tool_service_rpc_rejects_reserved_mcp_environment_sources() -> None:
    service = WorkerToolRuntimeService()
    try:
        sources = (
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id="reserved-stdio-rpc",
                enabled=True,
                stdio=tool_runtime_pb2.MCPStdioTransport(
                    command=sys.executable,
                    environment_references={"TOKEN": "PATH"},
                ),
            ),
            tool_runtime_pb2.AgentToolSourceConfig(
                source_id="reserved-http-rpc",
                enabled=True,
                streamable_http=tool_runtime_pb2.MCPStreamableHTTPTransport(
                    url="https://example.com/mcp",
                    header_environment_references={
                        "Authorization": "MELIX_GATEWAY_API_KEYS_JSON"
                    },
                ),
            ),
        )
        for source in sources:
            catalog = _list(service, source)
            assert catalog.live_source_count == 0
            assert catalog.sources[0].connection_state == "failed"
            assert catalog.sources[0].error_code == (
                "mcp_source_configuration_invalid"
            )
    finally:
        service.close()


def test_worker_tool_service_rpc_requires_restart_for_new_credential_source_key() -> None:
    service = WorkerToolRuntimeService(
        environment={
            "MELIX_MCP_CREDENTIAL_ENV_KEYS": "INITIAL_SECRET",
            "INITIAL_SECRET": "initial-value",
        }
    )
    try:
        source = tool_runtime_pb2.AgentToolSourceConfig(
            source_id="new-credential-key",
            enabled=True,
            stdio=tool_runtime_pb2.MCPStdioTransport(
                command=sys.executable,
                environment_references={"TOKEN": "NEW_SECRET"},
            ),
        )
        catalog = _list(service, source)
        assert catalog.live_source_count == 0
        assert catalog.sources[0].connection_state == "failed"
        assert catalog.sources[0].error_code == "mcp_source_configuration_invalid"
    finally:
        service.close()


def test_worker_tool_service_honors_expired_catalog_deadline() -> None:
    service = WorkerToolRuntimeService()
    try:
        with pytest.raises(futures.TimeoutError):
            service.ListAgentTools(
                tool_runtime_pb2.ListAgentToolsRequest(
                    deadline_unix_ms=int(time.time() * 1_000) - 1,
                ),
                None,
            )
    finally:
        service.close()


def test_worker_tool_service_rejects_execution_without_approval(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    try:
        catalog = _list(service, _source(tmp_path))
        add = _tool(catalog, "add")
        request = _execution_request(
            tool=add,
            call_id="service-denied",
            arguments={"a": 1, "b": 2},
        )
        request.context.admission_state = "ask"
        request.context.approval_grant_digest = ""

        events = list(service.ExecuteAgentTool(request, None))
        assert events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED
        )
        assert events[-1].error.code == "tool_admission_required"
        assert "approval" in events[-1].error.message.lower()
    finally:
        service.close()


def test_worker_tool_service_rejects_source_use_by_another_owner(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    try:
        catalog = _list(service, _source(tmp_path))
        add = _tool(catalog, "add")
        request = _execution_request(
            tool=add,
            call_id="wrong-owner-execution",
            arguments={"a": 1, "b": 2},
            actor_id="intruder",
        )
        events = list(service.ExecuteAgentTool(request, None))
        assert events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED
        )
        assert events[-1].error.code == "tool_owner_scope_mismatch"
    finally:
        service.close()


def test_worker_tool_service_source_lease_expires_and_release_is_terminal(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    source = _source(tmp_path)
    identity = common_pb2.RequestIdentity(
        session_id="lease-session",
        branch_id="lease-branch",
    )
    try:
        catalog = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=identity,
                sources=[source],
                owner_actor_id="lease-actor",
                lease_ttl_ms=100,
            ),
            None,
        )
        add = _tool(catalog, "add")
        time.sleep(0.15)
        expired = list(
            service.ExecuteAgentTool(
                _execution_request(
                    tool=add,
                    call_id="expired-lease",
                    arguments={"a": 20, "b": 22},
                    session_id="lease-session",
                    branch_id="lease-branch",
                    actor_id="lease-actor",
                ),
                None,
            )
        )
        assert expired[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_FAILED
        )
        expired_observation = json.loads(
            expired[-1].result.observation_json
        )
        assert expired_observation["payload"]["error_code"] == (
            "mcp_source_owner_scope_mismatch"
        )

        renewed = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=identity,
                sources=[source],
                owner_actor_id="lease-actor",
            ),
            None,
        )
        renewed_add = _tool(renewed, "add")
        service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=identity,
                owner_actor_id="lease-actor",
                release_sources=True,
            ),
            None,
        )
        released = list(
            service.ExecuteAgentTool(
                _execution_request(
                    tool=renewed_add,
                    call_id="released-lease",
                    arguments={"a": 20, "b": 22},
                    session_id="lease-session",
                    branch_id="lease-branch",
                    actor_id="lease-actor",
                ),
                None,
            )
        )
        assert released[-1].error.code == "tool_owner_scope_mismatch"
    finally:
        service.close()


def test_worker_tool_service_cancel_prevents_delayed_side_effect(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    output_path = tmp_path / "must-not-exist.txt"
    try:
        catalog = _list(service, _source(tmp_path))
        writer = _tool(catalog, "delayed_write")
        request = _execution_request(
            tool=writer,
            call_id="service-cancel",
                arguments={
                    "path": str(output_path),
                    # Keep the side effect comfortably beyond the polling
                    # window even under coverage instrumentation or host load.
                    "delay_ms": 10_000,
                },
            )
        captured_events = []

        def consume() -> None:
            captured_events.extend(
                service.ExecuteAgentTool(request, None)
            )

        execution_thread = threading.Thread(target=consume)
        execution_thread.start()
        for _ in range(100):
            if len(captured_events) >= 2:
                break
            time.sleep(0.01)
        assert len(captured_events) >= 2
        time.sleep(0.05)
        mismatched = service.CancelAgentTool(
            tool_runtime_pb2.CancelAgentToolRequest(
                run_id="service-run",
                call_id="service-cancel",
                cancellation_id="cancel-intruder",
                session_id="session",
                branch_id="branch",
                actor_id="intruder",
            ),
            None,
        )
        assert mismatched.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
        )
        assert mismatched.cancellation_id == "cancel-intruder"
        assert output_path.exists() is False
        receipt = None
        for _ in range(200):
            receipt = service.CancelAgentTool(
                tool_runtime_pb2.CancelAgentToolRequest(
                    run_id="service-run",
                    call_id="service-cancel",
                    cancellation_id="cancel-1",
                    session_id="session",
                    branch_id="branch",
                    actor_id="operator",
                ),
                None,
            )
            if receipt.disposition == (
                tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED
            ):
                break
            time.sleep(0.01)
        assert receipt is not None
        assert receipt.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_ACCEPTED
        )
        assert receipt.side_effect_state == (
            tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
        )
        assert receipt.cancellation_id == "cancel-1"

        execution_thread.join(timeout=10)
        assert execution_thread.is_alive() is False
        assert captured_events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_CANCELLED
        )
        time.sleep(0.1)
        assert output_path.exists() is False

        repeated = service.CancelAgentTool(
            tool_runtime_pb2.CancelAgentToolRequest(
                run_id="service-run",
                call_id="service-cancel",
                cancellation_id="cancel-2",
                session_id="session",
                branch_id="branch",
                actor_id="operator",
            ),
            None,
        )
        assert repeated.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_ALREADY_TERMINAL
        )
        assert repeated.cancellation_id == "cancel-2"
        assert repeated.side_effect_state == (
            tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
        )
    finally:
        service.close()


@pytest.mark.parametrize(
    "cancellation_id",
    ["", "   ", "cancel\x00invalid", "x" * 257],
)
def test_cancel_agent_tool_rejects_invalid_correlation_id(
    cancellation_id: str,
) -> None:
    service = WorkerToolRuntimeService()
    context = _DeadlineContext(None)
    try:
        with pytest.raises(ValueError, match="cancellation_id"):
            service.CancelAgentTool(
                tool_runtime_pb2.CancelAgentToolRequest(
                    run_id="service-run",
                    call_id="service-call",
                    cancellation_id=cancellation_id,
                    session_id="session",
                    branch_id="branch",
                    actor_id="operator",
                ),
                context,
            )
        assert context.aborted is not None
        assert context.aborted[0] == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        service.close()


def test_cancel_agent_tool_echoes_correlation_for_invalid_owner() -> None:
    service = WorkerToolRuntimeService()
    try:
        receipt = service.CancelAgentTool(
            tool_runtime_pb2.CancelAgentToolRequest(
                run_id="service-run",
                call_id="service-call",
                cancellation_id="cancel-invalid-owner",
                session_id="",
                branch_id="branch",
                actor_id="operator",
            ),
            None,
        )
        assert receipt.disposition == (
            tool_runtime_pb2.TOOL_CANCELLATION_SCOPE_MISMATCH
        )
        assert receipt.cancellation_id == "cancel-invalid-owner"
        assert receipt.side_effect_state == (
            tool_runtime_pb2.TOOL_SIDE_EFFECT_UNKNOWN
        )
    finally:
        service.close()


def test_refresh_does_not_tear_down_another_owner_active_call(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    output_path = tmp_path / "refresh-kept-active.txt"
    try:
        source = _source(tmp_path)
        first_catalog = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session-a",
                    branch_id="branch-a",
                ),
                sources=[source],
                owner_actor_id="operator-a",
            ),
            None,
        )
        conflicting_source = tool_runtime_pb2.AgentToolSourceConfig()
        conflicting_source.CopyFrom(source)
        conflicting_source.request_timeout_ms = 6_000
        conflict = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session-b",
                    branch_id="branch-b",
                ),
                sources=[conflicting_source],
                owner_actor_id="operator-b",
            ),
            None,
        )
        assert conflict.live_source_count == 0
        assert conflict.sources[0].connection_state == "failed"
        assert conflict.sources[0].error_code == "mcp_client_error"

        writer = _tool(first_catalog, "delayed_write")
        request = _execution_request(
            tool=writer,
            call_id="refresh-active-call",
            arguments={
                "path": str(output_path),
                "delay_ms": 250,
            },
            session_id="session-a",
            branch_id="branch-a",
            actor_id="operator-a",
        )
        captured_events = []

        execution_thread = threading.Thread(
            target=lambda: captured_events.extend(
                service.ExecuteAgentTool(request, None)
            )
        )
        execution_thread.start()
        for _ in range(100):
            if len(captured_events) >= 2:
                break
            time.sleep(0.01)
        assert len(captured_events) >= 2

        refreshed = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session-b",
                    branch_id="branch-b",
                ),
                sources=[source],
                refresh_sources=True,
                owner_actor_id="operator-b",
            ),
            None,
        )
        assert refreshed.live_source_count == 1
        execution_thread.join(timeout=10)
        assert execution_thread.is_alive() is False
        assert captured_events[-1].phase == (
            tool_runtime_pb2.AGENT_TOOL_EXECUTION_COMPLETED
        )
        assert output_path.read_text(encoding="utf-8") == "committed"

        service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session-b",
                    branch_id="branch-b",
                ),
                owner_actor_id="operator-b",
            ),
            None,
        )
        retained_for_first_owner = service.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    session_id="session-a",
                    branch_id="branch-a",
                ),
                sources=[source],
                owner_actor_id="operator-a",
            ),
            None,
        )
        assert retained_for_first_owner.live_source_count == 1
    finally:
        service.close()


def test_worker_tool_service_disconnect_cancels_active_execution(
    tmp_path: Path,
) -> None:
    service = WorkerToolRuntimeService()
    output_path = tmp_path / "disconnect-must-not-exist.txt"
    context = _DisconnectableContext()
    try:
        catalog = _list(service, _source(tmp_path))
        writer = _tool(catalog, "delayed_write")
        request = _execution_request(
            tool=writer,
            call_id="service-disconnect",
            arguments={
                "path": str(output_path),
                "delay_ms": 2_000,
            },
        )
        captured_events = []

        def consume() -> None:
            captured_events.extend(
                service.ExecuteAgentTool(request, context)
            )

        execution_thread = threading.Thread(target=consume)
        execution_thread.start()
        for _ in range(200):
            if len(captured_events) >= 2:
                break
            time.sleep(0.01)
        assert len(captured_events) >= 2

        context.disconnect()
        execution_thread.join(timeout=10)
        assert execution_thread.is_alive() is False
        time.sleep(0.1)
        assert output_path.exists() is False
    finally:
        service.close()
