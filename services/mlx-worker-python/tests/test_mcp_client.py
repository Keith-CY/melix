from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from worker.runtime import mcp_client as mcp_client_module
from worker.runtime.mcp_client import (
    MCPCallCancelledError,
    MCPClientError,
    MCPClientManager,
    MCPCancellationReceipt,
    MCPConnectionError,
    MCPServerCapabilities,
    MCPOwnerIdentity,
    MCPSourceConfigurationError,
    MCPSourceDefinition,
    MCPSourceNotInitializedError,
    MCPSourceOwnershipError,
    MCPStdioTransport,
    MCPStreamableHTTPTransport,
    MCPToolCatalog,
    MCPToolDefinition,
    MCPToolResult,
    MCPToolSchemaChangedError,
    MCPToolNotFoundError,
    MCPWireLimitError,
    _MCPSourceActor,
)


OWNER = MCPOwnerIdentity(
    session_id="session-owner",
    branch_id="branch-owner",
    actor_id="actor-owner",
)
OTHER_OWNER = MCPOwnerIdentity(
    session_id="session-other",
    branch_id="branch-other",
    actor_id="actor-other",
)


SERVER_SOURCE = """
from __future__ import annotations

import asyncio
import os
import sys

from mcp.server.fastmcp import FastMCP


port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--http" else 8000
server = FastMCP(
    "Melix MCP Contract Fixture",
    host="127.0.0.1",
    port=port,
    log_level="ERROR",
)


@server.tool()
def add(a: int, b: int) -> dict[str, int]:
    \"\"\"Add two integers.\"\"\"
    return {"sum": a + b}


@server.tool()
def environment_value() -> str:
    \"\"\"Return a fixture environment value.\"\"\"
    return os.environ.get("MCP_VISIBLE_VALUE", "missing")


@server.tool()
def huge_result(size: int) -> str:
    \"\"\"Return a large fixture string.\"\"\"
    return "x" * size


@server.tool()
async def slow(delay_ms: int) -> dict[str, int]:
    \"\"\"Wait long enough for cancellation tests.\"\"\"
    await asyncio.sleep(delay_ms / 1000)
    return {"delay_ms": delay_ms}


@server.tool()
def terminate_server() -> None:
    \"\"\"Terminate the fixture to exercise transport-loss handling.\"\"\"
    os._exit(17)


if len(sys.argv) > 1 and sys.argv[1] == "--http":
    server.run(transport="streamable-http")
else:
    sys.stderr.write(os.environ.get("MCP_VISIBLE_VALUE", "missing") + "\\n")
    sys.stderr.flush()
    server.run(transport="stdio")
"""


WIRE_ATTACK_SERVER_SOURCE = """
from __future__ import annotations

import json
import sys
import time


mode = sys.argv[1]
if mode == "no-newline":
    sys.stdout.buffer.write(b"x" * 2_048)
else:
    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0",
        "id": 0,
        "result": {"padding": "x" * 2_048},
    }) + "\\n")
sys.stdout.flush()
time.sleep(30)
"""


def _write_server(tmp_path: Path) -> Path:
    path = tmp_path / "mcp_contract_server.py"
    path.write_text(SERVER_SOURCE, encoding="utf-8")
    return path


def _write_wire_attack_server(tmp_path: Path) -> Path:
    path = tmp_path / "mcp_wire_attack_server.py"
    path.write_text(WIRE_ATTACK_SERVER_SOURCE, encoding="utf-8")
    return path


def _stdio_source(
    server_path: Path,
    *,
    result_limit: int = 262_144,
    credential_reference: bool = False,
) -> MCPSourceDefinition:
    return MCPSourceDefinition(
        source_id="contract-fixture",
        transport=MCPStdioTransport(
            command=sys.executable,
            arguments=(str(server_path),),
            working_directory=str(server_path.parent),
            environment_references=(
                {"MCP_VISIBLE_VALUE": "MELIX_TEST_MCP_SECRET"}
                if credential_reference
                else {}
            ),
        ),
        request_timeout_seconds=3,
        connect_timeout_seconds=30,
        max_result_bytes=result_limit,
        redaction_terms=("fixture-secret",),
    )


def _tool_by_name(catalog, name: str):
    return next(tool for tool in catalog.tools if tool.name == name)


class _ChunkedResponseStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def _wire_limited_http_client(
    transport: httpx.AsyncBaseTransport,
    failures: list[MCPWireLimitError],
) -> httpx.AsyncClient:
    async def enforce_limit(response: httpx.Response) -> None:
        await mcp_client_module._apply_http_wire_limits(
            response,
            source_id="http-wire",
            max_message_bytes=32,
            report_failure=failures.append,
        )

    return httpx.AsyncClient(
        transport=transport,
        event_hooks={"response": [enforce_limit]},
    )


def test_stdio_initializes_lists_and_calls_real_mcp_server(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager(
            environment={
                "MELIX_MCP_CREDENTIAL_ENV_KEYS": "MELIX_TEST_MCP_SECRET",
                "MELIX_TEST_MCP_SECRET": "fixture-secret",
            }
        )
        try:
            capabilities = await manager.initialize(
                _stdio_source(
                    _write_server(tmp_path),
                    credential_reference=True,
                ),
                OWNER,
            )
            assert capabilities.source_id == "contract-fixture"
            assert capabilities.transport_kind == "stdio"
            assert capabilities.server_name == "Melix MCP Contract Fixture"
            assert capabilities.tool_count == 5
            assert "tools" in capabilities.capability_names

            catalog = await manager.list_tools("contract-fixture", OWNER)
            add = _tool_by_name(catalog, "add")
            assert add.canonical_name == "mcp__contract-fixture__add"
            assert add.input_schema["required"] == ["a", "b"]
            assert len(add.schema_digest) == 64

            result = await manager.call_tool(
                "contract-fixture",
                owner=OWNER,
                run_id="run-contract",
                call_id="call-add",
                tool_name=add.canonical_name,
                arguments={"a": 20, "b": 22},
                expected_schema_digest=add.schema_digest,
            )
            assert result.is_error is False
            assert result.structured_content == {"sum": 42}
            assert result.truncated is False
            assert result.catalog_digest == catalog.catalog_digest
            assert result.duration_ms >= 0
        finally:
            await manager.close_all()

    asyncio.run(exercise())
    captured = capfd.readouterr()
    assert "fixture-secret" not in captured.out
    assert "fixture-secret" not in captured.err


def test_stdio_scrubs_environment_and_redacts_result(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager(
            environment={
                "MELIX_MCP_CREDENTIAL_ENV_KEYS": "MELIX_TEST_MCP_SECRET",
                "MELIX_TEST_MCP_SECRET": "fixture-secret",
                "UNREFERENCED_SECRET": "must-not-be-inherited",
            }
        )
        try:
            await manager.initialize(
                _stdio_source(
                    _write_server(tmp_path),
                    credential_reference=True,
                ),
                OWNER,
            )
            catalog = await manager.list_tools("contract-fixture", OWNER)
            tool = _tool_by_name(catalog, "environment_value")
            result = await manager.call_tool(
                "contract-fixture",
                owner=OWNER,
                run_id="run-contract",
                call_id="call-secret",
                tool_name=tool.name,
                arguments={},
                expected_schema_digest=tool.schema_digest,
            )
            encoded = json.dumps(
                {
                    "content": result.content,
                    "structured": result.structured_content,
                },
                sort_keys=True,
            )
            assert "fixture-secret" not in encoded
            assert "[REDACTED]" in encoded
            assert "must-not-be-inherited" not in encoded
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_resolved_transport_credentials_are_mandatory_redaction_terms(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        credential = "Bearer automatically-redacted-token"
        source = replace(
            _stdio_source(
                _write_server(tmp_path),
                credential_reference=True,
            ),
            redaction_terms=(),
        )
        manager = MCPClientManager(
            environment={
                "MELIX_MCP_CREDENTIAL_ENV_KEYS": "MELIX_TEST_MCP_SECRET",
                "MELIX_TEST_MCP_SECRET": credential,
            }
        )
        try:
            await manager.initialize(source, OWNER)
            catalog = await manager.list_tools(source.source_id, OWNER)
            tool = _tool_by_name(catalog, "environment_value")
            result = await manager.call_tool(
                source.source_id,
                owner=OWNER,
                run_id="run-auto-redaction",
                call_id="call-auto-redaction",
                tool_name=tool.name,
                arguments={},
                expected_schema_digest=tool.schema_digest,
            )
            encoded = json.dumps(
                {
                    "content": result.content,
                    "structured_content": result.structured_content,
                },
                sort_keys=True,
            )
            assert credential not in encoded
            assert "automatically-redacted-token" not in encoded
            assert "[REDACTED]" in encoded
        finally:
            await manager.close_all()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "credential_location",
    (
        "name",
        "title",
        "description",
        "input_schema",
        "output_schema",
        "annotations",
        "icons",
        "meta",
        "execution",
        "extra_metadata",
    ),
)
def test_resolved_credentials_cannot_reenter_tool_catalog_metadata(
    credential_location: str,
) -> None:
    async def exercise() -> None:
        credential = "catalog-secret-must-not-reenter"
        source = MCPSourceDefinition(
            source_id="credential-echo-fixture",
            transport=MCPStdioTransport(
                command=sys.executable,
                environment_references={
                    "MCP_CREDENTIAL": "PARENT_MCP_CREDENTIAL",
                },
            ),
        )
        actor = _MCPSourceActor(
            source,
            environment={"PARENT_MCP_CREDENTIAL": credential},
        )
        tool_payload = {
            "name": "safe_tool",
            "title": "Safe tool",
            "description": "Safe description",
            "inputSchema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
            },
            "outputSchema": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        }
        if credential_location in {"name", "title", "description"}:
            tool_payload[credential_location] = credential
        elif credential_location == "input_schema":
            tool_payload["inputSchema"]["properties"]["value"][
                "default"
            ] = credential
        elif credential_location == "output_schema":
            tool_payload["outputSchema"]["properties"]["result"][
                "default"
            ] = credential
        elif credential_location == "annotations":
            tool_payload["annotations"] = {"title": credential}
        elif credential_location == "icons":
            tool_payload["icons"] = [
                {"src": f"https://fixture.invalid/{credential}"}
            ]
        elif credential_location == "meta":
            tool_payload["_meta"] = {"credentialEcho": credential}
        elif credential_location == "execution":
            tool_payload["execution"] = {
                "taskSupport": "optional",
                "credentialEcho": credential,
            }
        else:
            tool_payload["credentialEcho"] = credential
        tool = mcp_client_module.mcp_types.Tool(**tool_payload)

        class CredentialEchoPage:
            async def list_tools(self, *, cursor):
                del cursor
                return SimpleNamespace(tools=[tool], nextCursor=None)

        with pytest.raises(MCPConnectionError, match="tool definition"):
            await actor._load_catalog(CredentialEchoPage())

    asyncio.run(exercise())


def test_resolved_credentials_cannot_reenter_server_metadata() -> None:
    credential = "server-secret-must-not-reenter"
    source = MCPSourceDefinition(
        source_id="server-credential-echo-fixture",
        transport=MCPStdioTransport(command=sys.executable),
    )
    initialized = mcp_client_module.mcp_types.InitializeResult(
        protocolVersion="2025-06-18",
        capabilities=mcp_client_module.mcp_types.ServerCapabilities(
            tools=mcp_client_module.mcp_types.ToolsCapability(
                listChanged=False,
            )
        ),
        serverInfo=mcp_client_module.mcp_types.Implementation(
            name=credential,
            title="Safe server",
            version="1",
        ),
    )
    catalog = MCPToolCatalog(
        source_id=source.source_id,
        tools=(),
        catalog_digest="empty-catalog",
        changed_since_initialize=False,
    )

    with pytest.raises(MCPConnectionError, match="server metadata"):
        mcp_client_module._server_capabilities(
            source,
            initialized,
            catalog,
            redaction_terms=(credential,),
        )


@pytest.mark.parametrize(
    "credential_location",
    (
        "server_title",
        "server_website",
        "server_icon",
        "server_extra",
        "instructions",
        "initialize_meta",
        "experimental_capability",
        "nested_capability_extra",
    ),
)
def test_resolved_credentials_cannot_reenter_nested_server_metadata(
    credential_location: str,
) -> None:
    credential = "nested-server-secret-must-not-reenter"
    source = MCPSourceDefinition(
        source_id="nested-server-credential-echo-fixture",
        transport=MCPStdioTransport(command=sys.executable),
    )
    server_info_payload = {
        "name": "Safe server",
        "title": "Safe title",
        "version": "1",
        "websiteUrl": "https://fixture.invalid",
        "icons": [{"src": "https://fixture.invalid/icon.png"}],
    }
    tools_payload = {"listChanged": False}
    capabilities_payload = {"tools": tools_payload}
    initialize_payload = {
        "protocolVersion": "2025-06-18",
        "capabilities": capabilities_payload,
        "serverInfo": server_info_payload,
        "instructions": "Safe instructions",
    }

    if credential_location == "server_title":
        server_info_payload["title"] = credential
    elif credential_location == "server_website":
        server_info_payload["websiteUrl"] = (
            f"https://fixture.invalid/{credential}"
        )
    elif credential_location == "server_icon":
        server_info_payload["icons"] = [
            {"src": f"https://fixture.invalid/{credential}"}
        ]
    elif credential_location == "server_extra":
        server_info_payload["credentialEcho"] = credential
    elif credential_location == "instructions":
        initialize_payload["instructions"] = credential
    elif credential_location == "initialize_meta":
        initialize_payload["_meta"] = {"credentialEcho": credential}
    elif credential_location == "experimental_capability":
        capabilities_payload["experimental"] = {
            "fixture": {"credentialEcho": credential}
        }
    else:
        tools_payload["credentialEcho"] = credential

    initialized = mcp_client_module.mcp_types.InitializeResult(
        **initialize_payload
    )
    catalog = MCPToolCatalog(
        source_id=source.source_id,
        tools=(),
        catalog_digest="empty-catalog",
        changed_since_initialize=False,
    )

    with pytest.raises(MCPConnectionError, match="server metadata"):
        mcp_client_module._server_capabilities(
            source,
            initialized,
            catalog,
            redaction_terms=(credential,),
        )


@pytest.mark.parametrize(
    ("mode", "expected_boundary"),
    (
        ("no-newline", "stdio frame"),
        ("huge-json-line", "stdio frame"),
    ),
    ids=("overlong-without-newline", "oversized-json-line"),
)
def test_stdio_wire_limit_precedes_json_parsing_and_fails_closed(
    tmp_path: Path,
    monkeypatch,
    mode: str,
    expected_boundary: str,
) -> None:
    def forbidden_json_parse(*args, **kwargs):
        del args, kwargs
        raise AssertionError("JSON/Pydantic parsing must stay behind wire bounds")

    monkeypatch.setattr(
        mcp_client_module,
        "_MAX_MCP_WIRE_MESSAGE_BYTES",
        1_024,
    )
    monkeypatch.setattr(
        mcp_client_module.mcp_types.JSONRPCMessage,
        "model_validate_json",
        forbidden_json_parse,
    )

    async def exercise() -> None:
        server_path = _write_wire_attack_server(tmp_path)
        source = MCPSourceDefinition(
            source_id="wire-attack",
            transport=MCPStdioTransport(
                command=sys.executable,
                arguments=(str(server_path), mode),
                working_directory=str(tmp_path),
            ),
            connect_timeout_seconds=10,
        )
        manager = MCPClientManager()
        started = time.perf_counter()
        try:
            with pytest.raises(
                MCPWireLimitError,
                match=expected_boundary,
            ) as captured:
                await manager.initialize(source, OWNER)
            assert captured.value.code == "mcp_wire_limit_exceeded"
            assert time.perf_counter() - started < 6
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_http_wire_limit_rejects_content_length_before_body_read() -> None:
    async def exercise() -> None:
        body = _ChunkedResponseStream(b"{}")

        async def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": "4096",
                },
                stream=body,
            )

        failures: list[MCPWireLimitError] = []
        client = _wire_limited_http_client(
            httpx.MockTransport(handler),
            failures,
        )
        async with client:
            with pytest.raises(MCPWireLimitError, match="Content-Length"):
                async with client.stream("GET", "https://mcp.invalid"):
                    raise AssertionError("oversized response must not open")
        assert body.closed is True
        assert len(failures) == 1
        assert failures[0].code == "mcp_wire_limit_exceeded"

    asyncio.run(exercise())


def test_http_wire_limit_rejects_ambiguous_lengths_and_compression() -> None:
    assert mcp_client_module._validated_content_length(httpx.Headers()) is None
    assert (
        mcp_client_module._validated_content_length(
            httpx.Headers({"Content-Length": "32, 32"})
        )
        == 32
    )
    assert (
        mcp_client_module._validated_content_length(
            httpx.Headers({"Content-Length": "9" * 21})
        )
        == 10**20
    )
    with pytest.raises(MCPWireLimitError, match="invalid Content-Length"):
        mcp_client_module._validated_content_length(
            httpx.Headers({"Content-Length": "-1"})
        )
    with pytest.raises(MCPWireLimitError, match="conflicting Content-Length"):
        mcp_client_module._validated_content_length(
            httpx.Headers(
                [
                    (b"content-length", b"31"),
                    (b"content-length", b"32"),
                ]
            )
        )

    async def exercise() -> None:
        body = _ChunkedResponseStream(b"compressed")

        async def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
                stream=body,
            )

        failures: list[MCPWireLimitError] = []
        client = _wire_limited_http_client(
            httpx.MockTransport(handler),
            failures,
        )
        async with client:
            with pytest.raises(MCPWireLimitError, match="compressed HTTP"):
                await client.get("https://mcp.invalid")
        assert body.closed is True
        assert len(failures) == 1

    asyncio.run(exercise())


def test_http_wire_limit_rejects_chunked_body_before_json_parse() -> None:
    async def exercise() -> None:
        body = _ChunkedResponseStream(b"{" + b"x" * 15, b"x" * 17)

        async def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                stream=body,
            )

        failures: list[MCPWireLimitError] = []
        client = _wire_limited_http_client(
            httpx.MockTransport(handler),
            failures,
        )
        async with client:
            with pytest.raises(MCPWireLimitError, match="response body"):
                async with client.stream(
                    "GET",
                    "https://mcp.invalid",
                ) as response:
                    await response.aread()
        assert body.closed is True
        assert len(failures) == 1

    asyncio.run(exercise())


def test_http_wire_limit_bounds_each_sse_event_not_whole_stream() -> None:
    async def exercise() -> None:
        small_events = _ChunkedResponseStream(
            b"data: {}\r",
            b"\n\r",
            b"\n" + b"data: {}\r\n\r\n" * 7,
        )
        oversized_event = _ChunkedResponseStream(
            b"data: " + b"x" * 12,
            b"x" * 20,
        )
        responses = iter((small_events, oversized_event))

        async def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=next(responses),
            )

        failures: list[MCPWireLimitError] = []
        client = _wire_limited_http_client(
            httpx.MockTransport(handler),
            failures,
        )
        async with client:
            first = await client.get("https://mcp.invalid")
            assert first.content == b"data: {}\r\n\r\n" * 8

            with pytest.raises(MCPWireLimitError, match="SSE event"):
                async with client.stream(
                    "GET",
                    "https://mcp.invalid",
                ) as response:
                    await response.aread()
        assert small_events.closed is True
        assert oversized_event.closed is True
        assert len(failures) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "boundary",
    (b"\n\n", b"\r\r", b"\r\n\r\n", b"\n\r\n", b"\r\n\n"),
)
def test_sse_wire_budget_recognizes_all_blank_line_encodings(
    boundary: bytes,
) -> None:
    budget = mcp_client_module._SSEEventByteBudget(
        source_id="sse-boundary",
        max_message_bytes=12,
    )
    for byte in b"data: x" + boundary + b"data: y" + boundary:
        budget.observe(bytes((byte,)))
    with pytest.raises(MCPWireLimitError, match="SSE event"):
        budget.observe(b"x" * 13)


def test_http_wire_failure_channel_is_fatal_when_sdk_swallows_stream_error() -> None:
    async def exercise() -> None:
        failure = asyncio.get_running_loop().create_future()
        blocked_operation = asyncio.Event()
        operation_task = asyncio.create_task(
            mcp_client_module._await_with_wire_failure(
                blocked_operation.wait(),
                failure,
            )
        )
        await asyncio.sleep(0)
        failure.set_result(
            MCPWireLimitError("MCP source 'fixture' SSE event exceeded 32 bytes")
        )
        with pytest.raises(MCPWireLimitError, match="SSE event"):
            await operation_task

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("response_kind", "expected_boundary"),
    (
        ("content-length", "Content-Length"),
        ("chunked-json", "response body"),
        ("chunked-sse", "SSE event"),
    ),
)
def test_live_http_client_preserves_typed_wire_failure_before_parsing(
    monkeypatch,
    response_kind: str,
    expected_boundary: str,
) -> None:
    def forbidden_json_parse(*args, **kwargs):
        del args, kwargs
        raise AssertionError("JSON/Pydantic parsing must stay behind wire bounds")

    monkeypatch.setattr(
        mcp_client_module,
        "_MAX_MCP_WIRE_MESSAGE_BYTES",
        32,
    )
    monkeypatch.setattr(
        mcp_client_module.mcp_types.JSONRPCMessage,
        "model_validate_json",
        forbidden_json_parse,
    )

    async def exercise() -> None:
        async def serve_attack(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                await reader.readuntil(b"\r\n\r\n")
                if response_kind == "content-length":
                    response = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json\r\n"
                        b"Content-Length: 4096\r\n"
                        b"Connection: close\r\n\r\n{}"
                    )
                else:
                    content_type = (
                        b"text/event-stream"
                        if response_kind == "chunked-sse"
                        else b"application/json"
                    )
                    payload = (
                        b"data: " + b"x" * 64
                        if response_kind == "chunked-sse"
                        else b"{" + b"x" * 64
                    )
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: "
                        + content_type
                        + b"\r\nTransfer-Encoding: chunked\r\n"
                        b"Connection: close\r\n\r\n"
                        + f"{len(payload):X}\r\n".encode("ascii")
                        + payload
                        + b"\r\n0\r\n\r\n"
                    )
                writer.write(response)
                await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                with suppress(ConnectionError):
                    await writer.wait_closed()

        server = await asyncio.start_server(
            serve_attack,
            "127.0.0.1",
            0,
        )
        port = server.sockets[0].getsockname()[1]
        manager = MCPClientManager()
        async with server:
            try:
                with pytest.raises(
                    MCPWireLimitError,
                    match=expected_boundary,
                ) as captured:
                    await manager.initialize(
                        MCPSourceDefinition(
                            source_id="live-http-wire",
                            transport=MCPStreamableHTTPTransport(
                                url=f"http://127.0.0.1:{port}/mcp"
                            ),
                            request_timeout_seconds=2,
                            connect_timeout_seconds=3,
                        ),
                        OWNER,
                    )
                assert captured.value.code == "mcp_wire_limit_exceeded"
            finally:
                await manager.close_all()

    asyncio.run(exercise())


def test_result_budget_precedes_model_dump_and_full_json(monkeypatch) -> None:
    text_item = mcp_client_module.mcp_types.TextContent(
        type="text",
        text="x" * 8_192,
    )

    def forbidden_model_dump(*args, **kwargs):
        del args, kwargs
        raise AssertionError("MCP result model_dump must stay behind bounds")

    monkeypatch.setattr(
        mcp_client_module.mcp_types.TextContent,
        "model_dump",
        forbidden_model_dump,
    )
    tool = mcp_client_module.MCPToolDefinition(
        source_id="budget-fixture",
        name="huge",
        canonical_name="mcp__budget-fixture__huge",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-budget",
    )
    source = MCPSourceDefinition(
        source_id="budget-fixture",
        transport=MCPStdioTransport(command=sys.executable),
        max_result_bytes=1_024,
    )
    result = mcp_client_module._normalize_result(
        source,
        tool=tool,
        call_id="call-budget",
        raw_result=SimpleNamespace(
            content=[text_item],
            structuredContent=None,
            isError=False,
        ),
        duration_ms=1,
        catalog_digest="catalog-budget",
    )
    assert result.truncated is True
    assert result.original_bytes > source.max_result_bytes
    assert result.emitted_bytes < source.max_result_bytes


def test_result_depth_budget_fails_closed_before_full_serialization() -> None:
    nested: dict[str, object] = {}
    current = nested
    for _ in range(64):
        child: dict[str, object] = {}
        current["child"] = child
        current = child
    source = MCPSourceDefinition(
        source_id="depth-fixture",
        transport=MCPStdioTransport(command=sys.executable),
        max_result_bytes=16_384,
    )
    tool = mcp_client_module.MCPToolDefinition(
        source_id=source.source_id,
        name="deep",
        canonical_name="mcp__depth-fixture__deep",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-depth",
    )
    result = mcp_client_module._normalize_result(
        source,
        tool=tool,
        call_id="call-depth",
        raw_result=SimpleNamespace(
            content=[],
            structuredContent=nested,
            isError=False,
        ),
        duration_ms=1,
        catalog_digest="catalog-depth",
    )
    assert result.truncated is True
    assert result.structured_content is not None
    assert result.structured_content["reason"] == "maximum_depth"


def test_result_node_budget_fails_closed_before_full_serialization() -> None:
    source = MCPSourceDefinition(
        source_id="node-fixture",
        transport=MCPStdioTransport(command=sys.executable),
        max_result_bytes=262_144,
    )
    tool = mcp_client_module.MCPToolDefinition(
        source_id=source.source_id,
        name="wide",
        canonical_name="mcp__node-fixture__wide",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-nodes",
    )
    result = mcp_client_module._normalize_result(
        source,
        tool=tool,
        call_id="call-nodes",
        raw_result=SimpleNamespace(
            content=[],
            structuredContent={str(index): index for index in range(5_000)},
            isError=False,
        ),
        duration_ms=1,
        catalog_digest="catalog-nodes",
    )
    assert result.truncated is True
    assert result.structured_content is not None
    assert result.structured_content["reason"] == "maximum_nodes"


@pytest.mark.parametrize(
    ("structured_content", "expected_reason"),
    [
        ({1: "non-string-key"}, "non_string_key"),
        ({"number": float("inf")}, "non_finite_number"),
        ({"opaque": object()}, "unsupported_result_type"),
    ],
)
def test_result_builder_rejects_unsafe_structured_values(
    structured_content: dict[object, object],
    expected_reason: str,
) -> None:
    source = MCPSourceDefinition(
        source_id="unsafe-result-fixture",
        transport=MCPStdioTransport(command=sys.executable),
        max_result_bytes=16_384,
    )
    tool = mcp_client_module.MCPToolDefinition(
        source_id=source.source_id,
        name="unsafe",
        canonical_name="mcp__unsafe-result-fixture__unsafe",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-unsafe",
    )
    result = mcp_client_module._normalize_result(
        source,
        tool=tool,
        call_id=f"call-{expected_reason}",
        raw_result=SimpleNamespace(
            content=[],
            structuredContent=structured_content,
            isError=False,
        ),
        duration_ms=1,
        catalog_digest="catalog-unsafe",
    )
    assert result.truncated is True
    assert result.structured_content is not None
    assert result.structured_content["reason"] == expected_reason


def test_result_builder_detects_cycles_and_omits_binary_payloads() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    builder = mcp_client_module._BoundedMCPResultBuilder(
        max_bytes=16_384,
        redaction_terms=(),
    )
    with pytest.raises(
        mcp_client_module._MCPResultBudgetExceeded,
        match="cyclic_result",
    ):
        builder.build(cyclic)

    normalized, _ = mcp_client_module._BoundedMCPResultBuilder(
        max_bytes=16_384,
        redaction_terms=(),
    ).build({"artifact": memoryview(b"private-binary")})
    assert normalized == {
        "artifact": {"binary_omitted": True, "byte_count": 14}
    }


def test_result_redaction_growth_is_charged_before_replacement() -> None:
    builder = mcp_client_module._BoundedMCPResultBuilder(
        max_bytes=1_024,
        redaction_terms=("x",),
    )
    with pytest.raises(
        mcp_client_module._MCPResultBudgetExceeded,
        match="maximum_bytes",
    ):
        builder.build({"echo": "x" * 200})
    assert builder.observed_bytes > 1_024


def test_result_limit_returns_bounded_truncation_receipt(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        try:
            await manager.initialize(
                _stdio_source(_write_server(tmp_path), result_limit=1_024),
                OWNER,
            )
            catalog = await manager.list_tools("contract-fixture", OWNER)
            tool = _tool_by_name(catalog, "huge_result")
            result = await manager.call_tool(
                "contract-fixture",
                owner=OWNER,
                run_id="run-contract",
                call_id="call-huge",
                tool_name=tool.name,
                arguments={"size": 8_192},
                expected_schema_digest=tool.schema_digest,
            )
            assert result.truncated is True
            assert result.original_bytes > 1_024
            assert result.emitted_bytes < 1_024
            assert result.structured_content is not None
            assert result.structured_content["truncated"] is True
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_schema_digest_mismatch_fails_closed_before_call(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        try:
            await manager.initialize(_stdio_source(_write_server(tmp_path)), OWNER)
            with pytest.raises(MCPToolSchemaChangedError):
                await manager.call_tool(
                    "contract-fixture",
                    owner=OWNER,
                    run_id="run-contract",
                    call_id="call-stale-schema",
                    tool_name="add",
                    arguments={"a": 1, "b": 2},
                    expected_schema_digest="0" * 64,
                )
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_active_stdio_call_cancels_and_connection_remains_usable(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        try:
            await manager.initialize(_stdio_source(_write_server(tmp_path)), OWNER)
            catalog = await manager.list_tools("contract-fixture", OWNER)
            slow = _tool_by_name(catalog, "slow")
            pending = asyncio.create_task(
                manager.call_tool(
                    "contract-fixture",
                    owner=OWNER,
                    run_id="run-contract",
                    call_id="call-slow",
                    tool_name=slow.name,
                    arguments={"delay_ms": 2_000},
                    expected_schema_digest=slow.schema_digest,
                )
            )
            await asyncio.sleep(0.05)

            receipt = None
            for _ in range(100):
                receipt = await manager.cancel(
                    "contract-fixture",
                    OWNER,
                    "run-contract",
                    "call-slow",
                )
                if receipt.disposition == "accepted":
                    break
                await asyncio.sleep(0.01)
            assert receipt is not None
            assert receipt.disposition == "accepted"
            assert receipt.run_id == "run-contract"
            assert receipt.side_effect_state == "unknown"
            assert receipt.propagation_acknowledged is True
            with pytest.raises(MCPCallCancelledError):
                await pending

            repeated = await manager.cancel(
                "contract-fixture",
                OWNER,
                "run-contract",
                "call-slow",
            )
            assert repeated.disposition == "already_terminal"
            assert repeated.propagation_acknowledged is False
            assert (
                manager.metrics_snapshot().cancel_propagation.invocation_count
                == 1
            )

            add = _tool_by_name(catalog, "add")
            result = await manager.call_tool(
                "contract-fixture",
                owner=OWNER,
                run_id="run-contract",
                call_id="call-after-cancel",
                tool_name=add.name,
                arguments={"a": 4, "b": 5},
                expected_schema_digest=add.schema_digest,
            )
            assert result.structured_content == {"sum": 9}
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_same_call_id_in_two_runs_cancels_only_the_matching_run(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        try:
            await manager.initialize(_stdio_source(_write_server(tmp_path)), OWNER)
            catalog = await manager.list_tools("contract-fixture", OWNER)
            slow = _tool_by_name(catalog, "slow")
            first = asyncio.create_task(
                manager.call_tool(
                    "contract-fixture",
                    owner=OWNER,
                    run_id="run-first",
                    call_id="shared-call-id",
                    tool_name=slow.name,
                    arguments={"delay_ms": 100},
                    expected_schema_digest=slow.schema_digest,
                )
            )
            second = asyncio.create_task(
                manager.call_tool(
                    "contract-fixture",
                    owner=OWNER,
                    run_id="run-second",
                    call_id="shared-call-id",
                    tool_name=slow.name,
                    arguments={"delay_ms": 2_000},
                    expected_schema_digest=slow.schema_digest,
                )
            )

            receipt = None
            for _ in range(100):
                receipt = await manager.cancel(
                    "contract-fixture",
                    OWNER,
                    "run-second",
                    "shared-call-id",
                )
                if receipt.disposition == "accepted":
                    break
                await asyncio.sleep(0.01)
            assert receipt is not None
            assert receipt.disposition == "accepted"
            assert receipt.side_effect_state == "none"
            first_result = await first
            assert first_result.structured_content == {"delay_ms": 100}
            with pytest.raises(MCPCallCancelledError):
                await second
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_force_close_preserves_caller_cancellation() -> None:
    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="close-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )
        release = asyncio.Event()

        async def cancellation_resistant_target() -> None:
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        target = asyncio.create_task(cancellation_resistant_target())
        actor._task = target
        close_task = asyncio.create_task(actor.force_close())
        await asyncio.sleep(0)
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task
        release.set()
        await target

    asyncio.run(exercise())


def test_active_cancel_reports_only_acknowledged_sdk_task_cancellation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_module,
        "_CANCEL_PROPAGATION_TIMEOUT_SECONDS",
        0.01,
    )

    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="cancel-ack-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )
        started = asyncio.Event()
        release = asyncio.Event()

        async def cancellation_resistant_target() -> None:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        target = asyncio.create_task(cancellation_resistant_target())
        await started.wait()
        actor._active_call_key = (OWNER.key, "run", "call")
        actor._active_call_task = target

        receipt = await actor.cancel(OWNER, "run", "call")

        assert receipt.disposition == "accepted"
        assert receipt.propagation_acknowledged is False
        assert target.done() is False
        release.set()
        await target

    asyncio.run(exercise())


def test_force_close_has_a_bounded_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client_module,
        "_SOURCE_CLOSE_TIMEOUT_SECONDS",
        0.01,
    )

    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="bounded-close-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )
        release = asyncio.Event()

        async def cancellation_resistant_target() -> None:
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        target = asyncio.create_task(cancellation_resistant_target())
        actor._task = target
        await asyncio.sleep(0)
        with pytest.raises(MCPConnectionError, match="did not close"):
            await actor.force_close()
        release.set()
        await target

    asyncio.run(exercise())


def test_actor_terminal_and_closing_guards() -> None:
    async def exercise() -> None:
        source = MCPSourceDefinition(
            source_id="actor-guard-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        actor = _MCPSourceActor(source, environment={})
        actor._closing = True
        with pytest.raises(MCPConnectionError, match="is closing"):
            await actor.list_tools()
        with pytest.raises(MCPConnectionError, match="is closing"):
            await actor.call_tool(
                owner=OWNER,
                run_id="run",
                call_id="call",
                tool_name="fixture",
                arguments={},
                expected_schema_digest="",
            )

        actor._closing = False
        with pytest.raises(MCPSourceNotInitializedError):
            await actor._await_response(
                asyncio.get_running_loop().create_future()
            )

        actor._ready = asyncio.get_running_loop().create_future()
        terminal_task = asyncio.create_task(asyncio.sleep(0))
        await terminal_task
        actor._task = terminal_task
        actor._failure = MCPConnectionError("terminal fixture")
        with pytest.raises(MCPConnectionError, match="terminal fixture"):
            await actor.start()

        response = asyncio.get_running_loop().create_future()
        with pytest.raises(MCPConnectionError, match="terminal fixture"):
            await actor._await_response(response)
        assert response.cancelled()

    asyncio.run(exercise())


def test_actor_close_cancels_active_call_and_bounds_transport_failure() -> None:
    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="actor-close-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )
        active_call = asyncio.create_task(asyncio.sleep(60))

        async def responsive_actor_loop() -> None:
            command = await actor._commands.get()
            assert isinstance(command, mcp_client_module._CloseCommand)
            command.response.set_result(None)

        actor._task = asyncio.create_task(responsive_actor_loop())
        actor._active_call_task = active_call
        await actor.close()
        with pytest.raises(asyncio.CancelledError):
            await active_call

        failed_actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="actor-failed-close-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )

        async def failed_actor_loop() -> None:
            await failed_actor._commands.get()
            raise MCPConnectionError("transport already failed")

        failed_actor._task = asyncio.create_task(failed_actor_loop())
        await failed_actor.force_close()

    asyncio.run(exercise())


def test_actor_command_error_boundaries(monkeypatch) -> None:
    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="actor-command-fixture",
                transport=MCPStdioTransport(command=sys.executable),
                request_timeout_seconds=0.01,
            ),
            environment={},
        )

        async def cancelled_catalog(session):
            del session
            raise asyncio.CancelledError

        actor._catalog_stale = True
        monkeypatch.setattr(actor, "_load_catalog", cancelled_catalog)
        response = asyncio.get_running_loop().create_future()
        command = mcp_client_module._ListCommand(True, response)
        with pytest.raises(asyncio.CancelledError):
            await actor._handle_list_command(None, command)
        response.cancel()

        async def rejected_catalog(session):
            del session
            raise MCPConnectionError("catalog rejected")

        actor._catalog_stale = True
        monkeypatch.setattr(actor, "_load_catalog", rejected_catalog)
        response = asyncio.get_running_loop().create_future()
        await actor._handle_list_command(
            None,
            mcp_client_module._ListCommand(True, response),
        )
        with pytest.raises(MCPConnectionError, match="catalog rejected"):
            await response

        async def broken_catalog(session):
            del session
            raise ValueError("broken catalog")

        actor._catalog_stale = True
        monkeypatch.setattr(actor, "_load_catalog", broken_catalog)
        response = asyncio.get_running_loop().create_future()
        with pytest.raises(MCPConnectionError, match="catalog request failed"):
            await actor._handle_list_command(
                None,
                mcp_client_module._ListCommand(True, response),
            )
        assert isinstance(response.exception(), MCPConnectionError)

        tool = mcp_client_module.MCPToolDefinition(
            source_id=actor.source.source_id,
            name="fixture",
            canonical_name="mcp__actor-command-fixture__fixture",
            title="",
            description="",
            input_schema={"type": "object"},
            output_schema=None,
            annotations={},
            schema_digest="schema-fixture",
        )
        actor._catalog = mcp_client_module.MCPToolCatalog(
            source_id=actor.source.source_id,
            tools=(tool,),
            catalog_digest="catalog-fixture",
            changed_since_initialize=False,
        )
        actor._catalog_stale = False

        class SlowSession:
            async def call_tool(self, *args, **kwargs):
                del args, kwargs
                await asyncio.sleep(60)

        response = asyncio.get_running_loop().create_future()
        await actor._handle_call_command(
            SlowSession(),
            mcp_client_module._CallCommand(
                owner=OWNER,
                run_id="run-timeout",
                call_id="call-timeout",
                tool_name=tool.name,
                arguments={},
                expected_schema_digest=tool.schema_digest,
                response=response,
            ),
        )
        assert isinstance(
            response.exception(),
            mcp_client_module.MCPCallTimeoutError,
        )

        class BrokenSession:
            def call_tool(self, *args, **kwargs):
                del args, kwargs
                return None

        response = asyncio.get_running_loop().create_future()
        with pytest.raises(MCPConnectionError, match="tool call failed"):
            await actor._handle_call_command(
                BrokenSession(),
                mcp_client_module._CallCommand(
                    owner=OWNER,
                    run_id="run-broken",
                    call_id="call-broken",
                    tool_name=tool.name,
                    arguments={},
                    expected_schema_digest=tool.schema_digest,
                    response=response,
                ),
            )
        assert isinstance(response.exception(), MCPConnectionError)

        actor._terminal_call_keys = {
            (OWNER.key, "run", f"call-{index}"): None
            for index in range(1_025)
        }
        response = asyncio.get_running_loop().create_future()
        response.cancel()
        await actor._handle_call_command(
            BrokenSession(),
            mcp_client_module._CallCommand(
                owner=OWNER,
                run_id="run-trim",
                call_id="call-trim",
                tool_name=tool.name,
                arguments={},
                expected_schema_digest=tool.schema_digest,
                response=response,
            ),
        )
        assert len(actor._terminal_call_keys) == 512
        assert (OWNER.key, "run-trim", "call-trim") in actor._terminal_call_keys

    asyncio.run(exercise())


def test_catalog_and_helper_safety_boundaries(monkeypatch) -> None:
    async def exercise() -> None:
        actor = _MCPSourceActor(
            MCPSourceDefinition(
                source_id="catalog-boundary-fixture",
                transport=MCPStdioTransport(command=sys.executable),
            ),
            environment={},
        )
        tool = mcp_client_module.mcp_types.Tool(
            name="fixture",
            inputSchema={"type": "object"},
        )

        class OneToolPage:
            async def list_tools(self, *, cursor):
                del cursor
                return SimpleNamespace(tools=[tool], nextCursor=None)

        original_tool_limit = mcp_client_module._MAX_CATALOG_TOOLS
        monkeypatch.setattr(mcp_client_module, "_MAX_CATALOG_TOOLS", 0)
        with pytest.raises(MCPConnectionError, match="tool catalog"):
            await actor._load_catalog(OneToolPage())
        monkeypatch.setattr(
            mcp_client_module,
            "_MAX_CATALOG_TOOLS",
            original_tool_limit,
        )

        class RepeatedCursorPage:
            async def list_tools(self, *, cursor):
                del cursor
                return SimpleNamespace(tools=[], nextCursor="repeat")

        with pytest.raises(MCPConnectionError, match="repeated"):
            await actor._load_catalog(RepeatedCursorPage())

        monkeypatch.setattr(mcp_client_module, "_MAX_CATALOG_PAGES", 1)
        with pytest.raises(MCPConnectionError, match="page count"):
            await actor._load_catalog(RepeatedCursorPage())

        original_definition_limit = (
            mcp_client_module._MAX_TOOL_DEFINITION_BYTES
        )
        monkeypatch.setattr(
            mcp_client_module,
            "_MAX_TOOL_DEFINITION_BYTES",
            32,
        )
        with pytest.raises(MCPConnectionError, match="tool definition"):
            await actor._load_catalog(OneToolPage())
        monkeypatch.setattr(
            mcp_client_module,
            "_MAX_TOOL_DEFINITION_BYTES",
            original_definition_limit,
        )

        original_catalog_bytes = mcp_client_module._MAX_CATALOG_BYTES
        monkeypatch.setattr(mcp_client_module, "_MAX_CATALOG_BYTES", 1)
        with pytest.raises(MCPConnectionError, match="catalog bytes"):
            await actor._load_catalog(OneToolPage())
        monkeypatch.setattr(
            mcp_client_module,
            "_MAX_CATALOG_BYTES",
            original_catalog_bytes,
        )

        with pytest.raises(MCPToolNotFoundError):
            actor._resolve_tool("missing")
        await actor._handle_message(
            mcp_client_module.mcp_types.ToolListChangedNotification()
        )
        assert actor._catalog_stale is True

        response = asyncio.get_running_loop().create_future()
        actor._queued_call_keys.add((OWNER.key, "run", "queued"))
        await actor._commands.put(
            mcp_client_module._CallCommand(
                owner=OWNER,
                run_id="run",
                call_id="queued",
                tool_name="fixture",
                arguments={},
                expected_schema_digest="",
                response=response,
            )
        )
        actor._fail_pending_commands(MCPConnectionError("closed"))
        assert (OWNER.key, "run", "queued") in actor._terminal_call_keys
        assert isinstance(response.exception(), MCPConnectionError)

    asyncio.run(exercise())

    assert len(
        mcp_client_module._canonical_tool_name(
            "source-" + ("x" * 64),
            "tool-" + ("y" * 64),
        )
    ) == 64
    with pytest.raises(MCPClientError, match="must be an object"):
        mcp_client_module._json_mapping([])
    assert mcp_client_module._redact(("secret",), ("secret",)) == (
        "[REDACTED]",
    )


def test_manager_cleans_failed_initialization(monkeypatch) -> None:
    async def failed_start(self):
        del self
        raise MCPConnectionError("startup failed")

    monkeypatch.setattr(_MCPSourceActor, "start", failed_start)

    async def exercise() -> None:
        manager = MCPClientManager()
        source = MCPSourceDefinition(
            source_id="failed-manager-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        with pytest.raises(MCPConnectionError, match="startup failed"):
            await manager.initialize(source, OWNER)
        assert source.source_id not in manager._actors
        assert source.source_id not in manager._configuration_digests
        with pytest.raises(MCPSourceOwnershipError):
            await manager.list_tools("missing-source", OWNER)

        closed: set[str] = set()

        class CloseFixture:
            def __init__(self, name: str, *, fails: bool = False) -> None:
                self.name = name
                self.fails = fails

            async def force_close(self) -> None:
                closed.add(self.name)
                if self.fails:
                    raise MCPConnectionError(f"{self.name} failed")

        manager._actors = {
            "first": CloseFixture("first", fails=True),
            "second": CloseFixture("second"),
        }
        with pytest.raises(MCPConnectionError, match="first failed"):
            await manager.close_all()
        assert closed == {"first", "second"}

    asyncio.run(exercise())


def test_manager_requires_restart_for_credential_key_added_after_worker_launch(
    monkeypatch,
) -> None:
    class FrozenCredentialActor:
        def __init__(self, source, *, environment) -> None:
            self.source = source
            self.environment = environment
            self.live = False

        @property
        def is_live(self) -> bool:
            return self.live

        async def start(self) -> MCPServerCapabilities:
            self.live = True
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name="fixture",
                server_version="1",
                capability_names=("tools",),
                tool_count=0,
                catalog_digest="catalog",
                connected_at_unix_ms=1,
            )

        async def force_close(self) -> None:
            self.live = False

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            FrozenCredentialActor,
        )
        manager = MCPClientManager(
            environment={
                "MELIX_MCP_CREDENTIAL_ENV_KEYS": "INITIAL_SECRET",
                "INITIAL_SECRET": "initial-value",
            }
        )
        initial_source = MCPSourceDefinition(
            source_id="initial-source",
            transport=MCPStdioTransport(
                command="/usr/bin/true",
                environment_references={"TOKEN": "INITIAL_SECRET"},
            ),
        )
        await manager.initialize(initial_source, OWNER)
        added_source = MCPSourceDefinition(
            source_id="added-source",
            transport=MCPStdioTransport(
                command="/usr/bin/true",
                environment_references={"TOKEN": "NEW_SECRET"},
            ),
        )
        with pytest.raises(MCPSourceConfigurationError, match="restart Melix"):
            await manager.initialize(added_source, OWNER)
        assert "added-source" not in manager._actors
        await manager.close_all()

    asyncio.run(exercise())


def test_manager_closes_actor_when_initialization_is_cancelled(monkeypatch) -> None:
    actors = []

    class CancelledInitializationActor:
        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source
            self.started = asyncio.Event()
            self.closed = asyncio.Event()
            actors.append(self)

        async def start(self):
            self.started.set()
            await asyncio.Event().wait()

        async def force_close(self) -> None:
            self.closed.set()

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            CancelledInitializationActor,
        )
        manager = MCPClientManager()
        source = MCPSourceDefinition(
            source_id="cancelled-initialize-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        initialize_task = asyncio.create_task(
            manager.initialize(source, OWNER)
        )
        while not actors:
            await asyncio.sleep(0)
        actor = actors[0]
        await actor.started.wait()
        initialize_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await initialize_task

        assert actor.closed.is_set()
        assert source.source_id not in manager._actors
        assert source.source_id not in manager._sources
        assert source.source_id not in manager._configuration_digests

    asyncio.run(exercise())


def test_source_b_initialization_does_not_block_source_a_cancellation(
    monkeypatch,
) -> None:
    source_b_started = asyncio.Event()
    allow_source_b_start = asyncio.Event()

    class IndependentSourceActor:
        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source
            self.live = False

        @property
        def is_live(self) -> bool:
            return self.live

        async def start(self) -> MCPServerCapabilities:
            if self.source.source_id == "source-b":
                source_b_started.set()
                await allow_source_b_start.wait()
            self.live = True
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name=self.source.source_id,
                server_version="1",
                capability_names=("tools",),
                tool_count=0,
                catalog_digest=f"catalog-{self.source.source_id}",
                connected_at_unix_ms=1,
            )

        async def cancel(self, owner, run_id, call_id) -> MCPCancellationReceipt:
            del owner
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                side_effect_state="unknown",
                propagation_acknowledged=True,
            )

        async def cancel_owner(self, owner) -> None:
            del owner

        async def force_close(self) -> None:
            self.live = False

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            IndependentSourceActor,
        )
        manager = MCPClientManager()
        source_a = MCPSourceDefinition(
            source_id="source-a",
            transport=MCPStdioTransport(command=sys.executable),
        )
        source_b = MCPSourceDefinition(
            source_id="source-b",
            transport=MCPStdioTransport(command=sys.executable),
        )
        try:
            await manager.initialize(source_a, OWNER)
            pending_initialize = asyncio.create_task(
                manager.initialize(source_b, OTHER_OWNER)
            )
            await source_b_started.wait()

            receipt = await asyncio.wait_for(
                manager.cancel(
                    source_a.source_id,
                    OWNER,
                    "run-a",
                    "call-a",
                ),
                timeout=0.1,
            )
            assert receipt.disposition == "accepted"

            allow_source_b_start.set()
            await pending_initialize
        finally:
            allow_source_b_start.set()
            await manager.close_all()

    asyncio.run(exercise())


def test_source_b_lease_cleanup_does_not_block_source_a_cancellation(
    monkeypatch,
) -> None:
    source_b_cleanup_started = asyncio.Event()
    allow_source_b_cleanup = asyncio.Event()

    class IndependentLeaseActor:
        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source
            self.live = False

        @property
        def is_live(self) -> bool:
            return self.live

        async def start(self) -> MCPServerCapabilities:
            self.live = True
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name=self.source.source_id,
                server_version="1",
                capability_names=("tools",),
                tool_count=0,
                catalog_digest=f"catalog-{self.source.source_id}",
                connected_at_unix_ms=1,
            )

        async def cancel(self, owner, run_id, call_id) -> MCPCancellationReceipt:
            del owner
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                side_effect_state="unknown",
                propagation_acknowledged=True,
            )

        async def cancel_owner(self, owner) -> None:
            del owner
            if self.source.source_id == "source-b":
                source_b_cleanup_started.set()
                await allow_source_b_cleanup.wait()

        async def force_close(self) -> None:
            self.live = False

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            IndependentLeaseActor,
        )
        manager = MCPClientManager()
        source_a = MCPSourceDefinition(
            source_id="source-a",
            transport=MCPStdioTransport(command=sys.executable),
        )
        source_b = MCPSourceDefinition(
            source_id="source-b",
            transport=MCPStdioTransport(command=sys.executable),
        )
        try:
            await manager.initialize(source_a, OWNER)
            await manager.initialize(source_b, OTHER_OWNER)
            pending_release = asyncio.create_task(
                manager.release(source_b.source_id, OTHER_OWNER)
            )
            await source_b_cleanup_started.wait()

            receipt = await asyncio.wait_for(
                manager.cancel(
                    source_a.source_id,
                    OWNER,
                    "run-a",
                    "call-a",
                ),
                timeout=0.1,
            )
            assert receipt.disposition == "accepted"

            allow_source_b_cleanup.set()
            assert await pending_release is True
        finally:
            allow_source_b_cleanup.set()
            await manager.close_all()

    asyncio.run(exercise())


def test_source_b_force_close_does_not_block_source_a_cancellation(
    monkeypatch,
) -> None:
    source_b_close_started = asyncio.Event()
    allow_source_b_close = asyncio.Event()

    class IndependentCloseActor:
        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source
            self.live = False

        @property
        def is_live(self) -> bool:
            return self.live

        async def start(self) -> MCPServerCapabilities:
            self.live = True
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name=self.source.source_id,
                server_version="1",
                capability_names=("tools",),
                tool_count=0,
                catalog_digest=f"catalog-{self.source.source_id}",
                connected_at_unix_ms=1,
            )

        async def cancel(self, owner, run_id, call_id) -> MCPCancellationReceipt:
            del owner
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="accepted",
                side_effect_state="unknown",
                propagation_acknowledged=True,
            )

        async def cancel_owner(self, owner) -> None:
            del owner

        async def force_close(self) -> None:
            if self.source.source_id == "source-b":
                source_b_close_started.set()
                await allow_source_b_close.wait()
            self.live = False

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            IndependentCloseActor,
        )
        manager = MCPClientManager()
        source_a = MCPSourceDefinition(
            source_id="source-a",
            transport=MCPStdioTransport(command=sys.executable),
        )
        source_b = MCPSourceDefinition(
            source_id="source-b",
            transport=MCPStdioTransport(command=sys.executable),
        )
        try:
            await manager.initialize(source_a, OWNER)
            await manager.initialize(source_b, OTHER_OWNER)
            pending_close = asyncio.create_task(manager.close(source_b.source_id))
            await source_b_close_started.wait()

            receipt = await asyncio.wait_for(
                manager.cancel(
                    source_a.source_id,
                    OWNER,
                    "run-a",
                    "call-a",
                ),
                timeout=0.1,
            )
            assert receipt.disposition == "accepted"

            allow_source_b_close.set()
            await pending_close
        finally:
            allow_source_b_close.set()
            await manager.close_all()

    asyncio.run(exercise())


def test_manager_metrics_snapshot_tracks_latency_reconnect_and_schema_changes(
    monkeypatch,
) -> None:
    class TickingClock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            self.value += 0.001
            return self.value

    tool = MCPToolDefinition(
        source_id="metrics-fixture",
        name="echo",
        canonical_name="mcp__metrics-fixture__echo",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-v2",
    )

    class FakeActor:
        catalog_version = 1

        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source
            self.live = True

        @property
        def is_live(self) -> bool:
            return self.live

        async def start(self) -> MCPServerCapabilities:
            digest = f"catalog-v{self.catalog_version}"
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name="metrics-fixture",
                server_version="1",
                capability_names=("tools",),
                tool_count=1,
                catalog_digest=digest,
                connected_at_unix_ms=1,
            )

        async def list_tools(self, *, refresh=False) -> MCPToolCatalog:
            if refresh:
                type(self).catalog_version = 2
            return MCPToolCatalog(
                source_id=self.source.source_id,
                tools=(tool,),
                catalog_digest=f"catalog-v{self.catalog_version}",
                changed_since_initialize=refresh,
            )

        async def call_tool(self, **kwargs) -> MCPToolResult:
            if kwargs["expected_schema_digest"] == "stale":
                raise MCPToolSchemaChangedError("schema changed")
            return MCPToolResult(
                source_id=self.source.source_id,
                tool_name="echo",
                call_id=kwargs["call_id"],
                content=(),
                structured_content={},
                is_error=False,
                original_bytes=2,
                emitted_bytes=2,
                truncated=False,
                duration_ms=1,
                catalog_digest=f"catalog-v{self.catalog_version}",
            )

        async def cancel(self, owner, run_id, call_id) -> MCPCancellationReceipt:
            del owner
            if call_id == "call-success":
                return MCPCancellationReceipt(
                    source_id=self.source.source_id,
                    run_id=run_id,
                    call_id=call_id,
                    disposition="accepted",
                    side_effect_state="unknown",
                    propagation_acknowledged=True,
                )
            return MCPCancellationReceipt(
                source_id=self.source.source_id,
                run_id=run_id,
                call_id=call_id,
                disposition="not_found",
                side_effect_state="none",
            )

        async def cancel_owner(self, owner) -> None:
            del owner

        async def force_close(self) -> None:
            self.live = False

    async def exercise() -> None:
        monkeypatch.setattr(mcp_client_module, "_MCPSourceActor", FakeActor)
        manager = MCPClientManager(latency_clock=TickingClock())
        source = MCPSourceDefinition(
            source_id="metrics-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        empty = manager.metrics_snapshot()
        assert empty.initialize.average_latency_ms == 0
        await manager.initialize(source, OWNER)
        await manager.list_tools(source.source_id, OWNER, refresh=True)
        with pytest.raises(MCPToolSchemaChangedError):
            await manager.call_tool(
                source.source_id,
                owner=OWNER,
                run_id="run-metrics",
                call_id="call-stale",
                tool_name=tool.name,
                arguments={},
                expected_schema_digest="stale",
            )
        await manager.call_tool(
            source.source_id,
            owner=OWNER,
            run_id="run-metrics",
            call_id="call-success",
            tool_name=tool.name,
            arguments={},
        )
        await manager.cancel(
            source.source_id,
            OWNER,
            "run-metrics",
            "call-success",
        )
        await manager.cancel(
            source.source_id,
            OWNER,
            "run-metrics",
            "missing-call",
        )
        manager._actors[source.source_id].live = False
        await manager.list_tools(source.source_id, OWNER)

        snapshot = manager.metrics_snapshot()
        assert snapshot.schema_version == "melix.mcp_client_metrics.v1"
        assert not hasattr(snapshot, "__dict__")
        assert snapshot.initialize.invocation_count == 2
        assert snapshot.list_tools.invocation_count == 2
        assert snapshot.call_tool.invocation_count == 2
        assert snapshot.call_tool.failure_count == 1
        assert snapshot.cancel_propagation.invocation_count == 1
        assert snapshot.reconnect_count == 1
        assert snapshot.schema_change_count == 2
        for operation in (
            snapshot.initialize,
            snapshot.list_tools,
            snapshot.call_tool,
            snapshot.cancel_propagation,
        ):
            assert not hasattr(operation, "__dict__")
            assert operation.average_latency_ms > 0
            assert operation.maximum_latency_ms >= operation.last_latency_ms
        await manager.close_all()

    asyncio.run(exercise())


def test_source_leases_isolate_owners_and_release_or_expire(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        now = [100.0]
        manager = MCPClientManager(monotonic_clock=lambda: now[0])
        source = _stdio_source(_write_server(tmp_path))
        try:
            await manager.initialize(
                source,
                OWNER,
                lease_ttl_seconds=10,
            )
            with pytest.raises(MCPSourceOwnershipError, match="not leased"):
                await manager.list_tools(source.source_id, OTHER_OWNER)

            await manager.initialize(
                source,
                OTHER_OWNER,
                lease_ttl_seconds=20,
            )
            assert (
                await manager.list_tools(source.source_id, OTHER_OWNER)
            ).tools

            changed_source = replace(source, request_timeout_seconds=4)
            with pytest.raises(
                MCPSourceOwnershipError,
                match="another owner lease",
            ):
                await manager.initialize(changed_source, OWNER)

            assert await manager.release(source.source_id, OWNER) is True
            with pytest.raises(MCPSourceOwnershipError, match="not leased"):
                await manager.list_tools(source.source_id, OWNER)
            assert (
                await manager.list_tools(source.source_id, OTHER_OWNER)
            ).tools

            now[0] = 121.0
            with pytest.raises(MCPSourceOwnershipError, match="not leased"):
                await manager.list_tools(source.source_id, OTHER_OWNER)
            assert not manager._leases
            assert source.source_id not in manager._actors
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_missing_actor_cannot_bypass_another_owner_configuration_lease() -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        source = MCPSourceDefinition(
            source_id="missing-actor-lease-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        changed_source = replace(source, request_timeout_seconds=4)
        manager._sources[source.source_id] = source
        manager._configuration_digests[source.source_id] = (
            source.configuration_digest
        )
        manager._leases[(source.source_id, OTHER_OWNER.key)] = (
            mcp_client_module._MCPSourceLease(
                owner=OTHER_OWNER,
                configuration_digest=source.configuration_digest,
                expires_at_monotonic=manager._monotonic_clock() + 60,
            )
        )
        try:
            with pytest.raises(
                MCPSourceOwnershipError,
                match="another owner lease",
            ):
                await manager.initialize(changed_source, OWNER)
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_expired_lease_sweeper_closes_idle_source(monkeypatch) -> None:
    closed = asyncio.Event()

    class SweeperActor:
        def __init__(self, source, *, environment) -> None:
            del environment
            self.source = source

        @property
        def is_live(self) -> bool:
            return not closed.is_set()

        async def start(self) -> MCPServerCapabilities:
            return MCPServerCapabilities(
                source_id=self.source.source_id,
                transport_kind="stdio",
                protocol_version="1",
                server_name="sweeper-fixture",
                server_version="1",
                capability_names=("tools",),
                tool_count=0,
                catalog_digest="sweeper-catalog",
                connected_at_unix_ms=1,
            )

        async def cancel_owner(self, owner) -> None:
            del owner

        async def force_close(self) -> None:
            closed.set()

    async def exercise() -> None:
        monkeypatch.setattr(
            mcp_client_module,
            "_MCPSourceActor",
            SweeperActor,
        )
        manager = MCPClientManager()
        source = MCPSourceDefinition(
            source_id="sweeper-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        try:
            await manager.initialize(
                source,
                OWNER,
                lease_ttl_seconds=0.05,
            )
            for _ in range(100):
                if source.source_id not in manager._actors:
                    break
                await asyncio.sleep(0.01)
            assert source.source_id not in manager._actors
            assert source.source_id not in manager._sources
            assert not manager._leases
            assert closed.is_set()
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_mcp_cancellation_is_bound_to_exact_owner(tmp_path: Path) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        source = _stdio_source(_write_server(tmp_path))
        try:
            await manager.initialize(source, OWNER)
            await manager.initialize(source, OTHER_OWNER)
            catalog = await manager.list_tools(source.source_id, OWNER)
            slow = _tool_by_name(catalog, "slow")
            pending = asyncio.create_task(
                manager.call_tool(
                    source.source_id,
                    owner=OWNER,
                    run_id="owner-run",
                    call_id="owner-call",
                    tool_name=slow.name,
                    arguments={"delay_ms": 2_000},
                    expected_schema_digest=slow.schema_digest,
                )
            )
            await asyncio.sleep(0.05)
            wrong_owner = await manager.cancel(
                source.source_id,
                OTHER_OWNER,
                "owner-run",
                "owner-call",
            )
            assert wrong_owner.disposition == "scope_mismatch"
            assert pending.done() is False

            accepted = await manager.cancel(
                source.source_id,
                OWNER,
                "owner-run",
                "owner-call",
            )
            assert accepted.disposition == "accepted"
            with pytest.raises(MCPCallCancelledError):
                await pending
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_stdio_disconnect_fails_bounded_and_next_call_reconnects(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        source = _stdio_source(_write_server(tmp_path))
        try:
            await manager.initialize(source, OWNER)
            catalog = await manager.list_tools("contract-fixture", OWNER)
            terminate = _tool_by_name(catalog, "terminate_server")
            with pytest.raises(MCPConnectionError):
                await asyncio.wait_for(
                    manager.call_tool(
                        "contract-fixture",
                        owner=OWNER,
                        run_id="run-contract",
                        call_id="call-terminate",
                        tool_name=terminate.name,
                        arguments={},
                        expected_schema_digest=terminate.schema_digest,
                    ),
                    timeout=3,
                )

            for _ in range(2):
                try:
                    catalog = await asyncio.wait_for(
                        manager.list_tools("contract-fixture", OWNER),
                        # A reconnect includes a cold Python/MCP server start;
                        # keep it bounded without conflating import latency
                        # with transport-recovery correctness.
                        timeout=20,
                    )
                    break
                except MCPConnectionError:
                    await asyncio.sleep(0)
            else:
                raise AssertionError("MCP source did not reconnect after transport loss")

            add = _tool_by_name(catalog, "add")
            result = await asyncio.wait_for(
                manager.call_tool(
                    "contract-fixture",
                    owner=OWNER,
                    run_id="run-contract",
                    call_id="call-after-reconnect",
                    tool_name=add.name,
                    arguments={"a": 19, "b": 23},
                    expected_schema_digest=add.schema_digest,
                ),
                timeout=3,
            )
            assert result.structured_content == {"sum": 42}
        finally:
            await manager.close_all()

    asyncio.run(exercise())


def test_streamable_http_initializes_and_calls_real_server(
    tmp_path: Path,
) -> None:
    server_path = _write_server(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    process = subprocess.Popen(
        [sys.executable, str(server_path), "--http", str(port)],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if process.poll() is not None:
                    raise AssertionError("MCP HTTP fixture exited before startup")
                time.sleep(0.05)
        else:
            raise AssertionError("MCP HTTP fixture did not start")

        async def exercise() -> None:
            manager = MCPClientManager()
            try:
                capabilities = await manager.initialize(
                    MCPSourceDefinition(
                        source_id="http-fixture",
                        transport=MCPStreamableHTTPTransport(
                            url=f"http://127.0.0.1:{port}/mcp"
                        ),
                        request_timeout_seconds=3,
                        connect_timeout_seconds=10,
                    ),
                    OWNER,
                )
                assert capabilities.transport_kind == "streamable_http"
                catalog = await manager.list_tools("http-fixture", OWNER)
                add = _tool_by_name(catalog, "add")
                result = await manager.call_tool(
                    "http-fixture",
                    owner=OWNER,
                    run_id="run-http",
                    call_id="call-http-add",
                    tool_name=add.name,
                    arguments={"a": 11, "b": 31},
                    expected_schema_digest=add.schema_digest,
                )
                assert result.structured_content == {"sum": 42}
            finally:
                await manager.close_all()

        asyncio.run(exercise())
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    "source",
    [
        lambda: MCPSourceDefinition(
            source_id="Has Spaces",
            transport=MCPStdioTransport(command="python"),
        ),
        lambda: MCPSourceDefinition(
            source_id="relative-cwd",
            transport=MCPStdioTransport(
                command="python",
                working_directory="relative",
            ),
        ),
        lambda: MCPSourceDefinition(
            source_id="insecure-http",
            transport=MCPStreamableHTTPTransport(
                url="http://example.com/mcp"
            ),
        ),
    ],
)
def test_invalid_source_configuration_fails_closed(source) -> None:
    with pytest.raises(MCPSourceConfigurationError):
        source()


@pytest.mark.parametrize(
    "source",
    [
        lambda: MCPSourceDefinition(
            source_id="request-timeout",
            transport=MCPStdioTransport(command="python"),
            request_timeout_seconds=0,
        ),
        lambda: MCPSourceDefinition(
            source_id="connect-timeout",
            transport=MCPStdioTransport(command="python"),
            connect_timeout_seconds=0,
        ),
        lambda: MCPSourceDefinition(
            source_id="result-limit",
            transport=MCPStdioTransport(command="python"),
            max_result_bytes=1_023,
        ),
        lambda: MCPSourceDefinition(
            source_id="result-limit-too-large",
            transport=MCPStdioTransport(command="python"),
            max_result_bytes=16 * 1_024 * 1_024 + 1,
        ),
        lambda: MCPSourceDefinition(
            source_id="blank-command",
            transport=MCPStdioTransport(command=" "),
        ),
        lambda: MCPSourceDefinition(
            source_id="nul-command",
            transport=MCPStdioTransport(command="python\x00bad"),
        ),
        lambda: MCPSourceDefinition(
            source_id="relative-http",
            transport=MCPStreamableHTTPTransport(url="/mcp"),
        ),
    ],
)
def test_additional_invalid_source_configuration_is_rejected(source) -> None:
    with pytest.raises(MCPSourceConfigurationError):
        source()


@pytest.mark.parametrize(
    ("url", "expected_message"),
    [
        ("https://operator@example.com/mcp", "must not contain userinfo"),
        (
            "https://operator:secret@example.com/mcp",
            "must not contain userinfo",
        ),
        ("https://example.com/mcp#result", "must not contain a fragment"),
        ("https://example.com/mcp#", "must not contain a fragment"),
    ],
)
def test_http_source_rejects_url_userinfo_and_fragments(
    url: str,
    expected_message: str,
) -> None:
    with pytest.raises(MCPSourceConfigurationError, match=expected_message):
        MCPSourceDefinition(
            source_id="unsafe-http-url",
            transport=MCPStreamableHTTPTransport(url=url),
        )


@pytest.mark.parametrize(
    "header",
    ["Authorization", "Cookie", "X-API-Key", "X-Private-Key"],
)
def test_http_source_requires_environment_references_for_credentials(
    header: str,
) -> None:
    with pytest.raises(
        MCPSourceConfigurationError,
        match="credential headers must use environment references",
    ):
        MCPSourceDefinition(
            source_id="static-http-credential",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers={header: "must-not-be-stored"},
            ),
        )


@pytest.mark.parametrize(
    "transport",
    [
        MCPStdioTransport(
            command="python",
            environment_references={"TOKEN": "PATH"},
        ),
        MCPStdioTransport(
            command="python",
            environment_references={
                "TOKEN": "MELIX_GATEWAY_API_KEYS_JSON"
            },
        ),
        MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={
                "Authorization": "MELIX_ACTIVE_RUNTIME_PATH"
            },
        ),
    ],
)
def test_source_admission_rejects_reserved_process_environment_references(
    transport: MCPStdioTransport | MCPStreamableHTTPTransport,
) -> None:
    with pytest.raises(
        MCPSourceConfigurationError,
        match="reserved Melix process key",
    ):
        MCPSourceDefinition(
            source_id="reserved-environment-source",
            transport=transport,
        )


def test_source_admission_rejects_exec_unsafe_environment_key_bytes() -> None:
    with pytest.raises(
        MCPSourceConfigurationError,
        match="invalid environment reference",
    ):
        MCPSourceDefinition(
            source_id="oversized-environment-key",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                header_environment_references={
                    "Authorization": "A" * 256
                },
            ),
        )


@pytest.mark.parametrize(
    "transport",
    (
        MCPStdioTransport(
            command="python",
            environment_references={"A" * 256: "SECRET"},
        ),
        MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={"X" * 256: "SECRET"},
        ),
        MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={"Bad Header": "SECRET"},
        ),
        MCPStdioTransport(
            command="python",
            environment_references={
                f"KEY_{index}_" + "A" * (247 - len(str(index))): "SECRET"
                for index in range(130)
            },
        ),
        MCPStdioTransport(
            command="python",
            environment_references={
                f"TOKEN_{index}": "SECRET"
                for index in range(1_025)
            },
        ),
    ),
)
def test_source_admission_rejects_exec_unsafe_reference_target_bytes(
    transport: MCPStdioTransport | MCPStreamableHTTPTransport,
) -> None:
    with pytest.raises(MCPSourceConfigurationError):
        MCPSourceDefinition(
            source_id="oversized-reference-target",
            transport=transport,
        )


def test_source_admission_rejects_combined_http_header_budget_and_name_conflict() -> None:
    with pytest.raises(MCPSourceConfigurationError, match="transport limit"):
        MCPSourceDefinition(
            source_id="combined-header-budget",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers={
                    f"X-Static-{index}": "visible" for index in range(600)
                },
                header_environment_references={
                    f"X-Secret-{index}": "SECRET" for index in range(600)
                },
            ),
        )
    with pytest.raises(MCPSourceConfigurationError, match="conflict"):
        MCPSourceDefinition(
            source_id="conflicting-header-name",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers={"X-Custom": "visible"},
                header_environment_references={"x-custom": "SECRET"},
            ),
        )


@pytest.mark.parametrize("header_name", ("Bad Header", "Bad:Header", "Bad\r\nHeader"))
def test_source_admission_rejects_invalid_static_http_header_names(
    header_name: str,
) -> None:
    with pytest.raises(MCPSourceConfigurationError, match="header name is invalid"):
        MCPSourceDefinition(
            source_id="invalid-static-header",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers={header_name: "visible"},
            ),
        )


@pytest.mark.parametrize(
    "headers",
    (
        {
            f"X-Key-{index}-" + "A" * (245 - len(str(index))): "visible"
            for index in range(130)
        },
        {f"X-Key-{index}": "visible" for index in range(1_025)},
    ),
)
def test_source_admission_rejects_exec_unsafe_static_http_header_sets(
    headers: dict[str, str],
) -> None:
    with pytest.raises(MCPSourceConfigurationError):
        MCPSourceDefinition(
            source_id="unsafe-static-header-set",
            transport=MCPStreamableHTTPTransport(
                url="https://example.com/mcp",
                headers=headers,
            ),
        )


def test_transport_credentials_resolve_only_explicit_references() -> None:
    stdio = MCPStdioTransport(
        command="python",
        environment_references={"CHILD_TOKEN": "PARENT_TOKEN"},
    )
    assert stdio.resolved_environment(
        {"PARENT_TOKEN": "secret", "UNRELATED": "hidden"}
    ) == {"CHILD_TOKEN": "secret"}
    assert stdio.resolved_environment({}) == {}
    with pytest.raises(MCPSourceConfigurationError):
        MCPStdioTransport(
            command="python",
            environment_references={"bad-key": "PARENT_TOKEN"},
        ).resolved_environment({})
    with pytest.raises(MCPSourceConfigurationError):
        MCPStdioTransport(
            command="python",
            environment_references={"CHILD_TOKEN": "bad-parent"},
        ).resolved_environment({})

    http = MCPStreamableHTTPTransport(
        url="https://example.com/mcp",
        headers={" X-Static ": "visible", " ": "ignored"},
        header_environment_references={
            "Authorization": "PARENT_TOKEN"
        },
    )
    assert http.resolved_headers({"PARENT_TOKEN": "secret"}) == {
        "X-Static": "visible",
        "Authorization": "secret",
    }
    assert "Authorization" not in http.resolved_headers({})
    with pytest.raises(MCPSourceConfigurationError):
        MCPSourceDefinition(
            source_id="invalid-static-http-headers",
            transport=http,
        )
    MCPSourceDefinition(
        source_id="safe-http-headers",
        transport=MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            headers={"X-Static": "visible"},
            header_environment_references={"Authorization": "PARENT_TOKEN"},
        ),
    )
    with pytest.raises(MCPSourceConfigurationError):
        MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={" ": "PARENT_TOKEN"},
        ).resolved_headers({})
    with pytest.raises(MCPSourceConfigurationError):
        MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={"Authorization": "bad-parent"},
        ).resolved_headers({})


def test_resolved_http_header_credential_is_enforced_in_result_redaction() -> None:
    credential = "Bearer header-secret-must-not-reenter"
    source = MCPSourceDefinition(
        source_id="header-redaction-fixture",
        transport=MCPStreamableHTTPTransport(
            url="https://example.com/mcp",
            header_environment_references={
                "Authorization": "MCP_AUTHORIZATION"
            },
        ),
    )
    actor = _MCPSourceActor(
        source,
        environment={"MCP_AUTHORIZATION": credential},
    )
    assert credential in actor._redaction_terms
    assert "header-secret-must-not-reenter" in actor._redaction_terms
    tool = mcp_client_module.MCPToolDefinition(
        source_id=source.source_id,
        name="echo",
        canonical_name="mcp__header-redaction-fixture__echo",
        title="",
        description="",
        input_schema={"type": "object"},
        output_schema=None,
        annotations={},
        schema_digest="schema-header-redaction",
    )
    result = mcp_client_module._normalize_result(
        source,
        tool=tool,
        call_id="call-header-redaction",
        raw_result=SimpleNamespace(
            content=[
                mcp_client_module.mcp_types.TextContent(
                    type="text",
                    text=credential,
                )
            ],
            structuredContent={"echo": "header-secret-must-not-reenter"},
            isError=False,
        ),
        duration_ms=1,
        catalog_digest="catalog-header-redaction",
        redaction_terms=actor._redaction_terms,
    )
    encoded = json.dumps(
        {
            "content": result.content,
            "structured_content": result.structured_content,
        },
        sort_keys=True,
    )
    assert credential not in encoded
    assert "header-secret-must-not-reenter" not in encoded
    assert "[REDACTED]" in encoded


def test_manager_rejects_blank_call_identity_and_unknown_source() -> None:
    async def exercise() -> None:
        manager = MCPClientManager()
        with pytest.raises(MCPSourceConfigurationError, match="run_id"):
            await manager.call_tool(
                "missing",
                owner=OWNER,
                run_id=" ",
                call_id="call",
                tool_name="tool",
                arguments={},
            )
        with pytest.raises(MCPSourceConfigurationError, match="call_id"):
            await manager.call_tool(
                "missing",
                owner=OWNER,
                run_id="run",
                call_id=" ",
                tool_name="tool",
                arguments={},
            )
        with pytest.raises(MCPSourceOwnershipError):
            await manager.cancel("missing", OWNER, "run", "call")
        await manager.close("missing")
        await manager.close_all()

    asyncio.run(exercise())


def test_owner_identity_and_lease_ttl_fail_closed() -> None:
    for values in (
        ("", "branch", "actor"),
        ("session", "", "actor"),
        ("session", "branch", ""),
        ("session", "branch", "x" * 257),
    ):
        with pytest.raises(MCPSourceOwnershipError):
            MCPOwnerIdentity(*values)

    async def exercise() -> None:
        manager = MCPClientManager()
        source = MCPSourceDefinition(
            source_id="ttl-fixture",
            transport=MCPStdioTransport(command=sys.executable),
        )
        for ttl in (0, -1, 3_601):
            with pytest.raises(MCPSourceOwnershipError, match="lease TTL"):
                await manager.initialize(
                    source,
                    OWNER,
                    lease_ttl_seconds=ttl,
                )
        await manager.close_all()

    asyncio.run(exercise())
