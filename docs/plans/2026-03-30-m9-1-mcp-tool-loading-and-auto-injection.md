# M9.1 MCP Tool Loading And Auto-Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-owned MCP configuration loading and deterministic tool auto-injection so Melix can expose supported MCP-backed tools to local runtime consumers without hiding the active tool sources.

**Architecture:** Keep MCP state in the Swift control plane, load it from explicit configuration inputs, and resolve tool availability before request shaping so auto-injected tools reuse the existing parser and stream surfaces. Expose effective MCP source state through control-plane snapshots and lightweight operator-visible metadata, but defer the full settings editor to later gateway-configuration work.

**Tech Stack:** Swift 6, Swift Protobuf, XCTest, integration tests, repository-owned runbooks and smoke scripts.

---

## Scope Notes

- Treat MCP configuration as a typed Melix-owned input, not an opaque passthrough string.
- Keep parser mode selection separate from MCP tool-source selection; parser choice explains how tools are emitted, MCP explains which tools are eligible.
- Operator control in this slice means explicit enabled or disabled state and snapshot visibility, not full UI editing.
- High-risk MCP namespaces are not exposed by default. Operators must opt exact namespaces into
  auto-injection with `MELIX_MCP_HIGH_RISK_ALLOWLIST`, and snapshots must expose the requested
  policy, effective policy, override source, and refused namespaces.

## Performance Probes And Success Metrics

- `mcp.tool_injection_success_rate`
- `mcp.config_load_latency_ms`
- `mcp.configured_tool_count`
- `mcp.disabled_tool_source_count`
- `mcp.refused_tool_count`

## Task 1: Add Typed MCP Configuration And Snapshot Visibility

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/descriptors/melix.pb`
- Modify: `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- Modify: `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- Modify: `packages/protocol/python/controlplane/v1/control_plane_pb2_grpc.py`
- Add: `services/control-plane-swift/Sources/Requests/MCPToolCatalog.swift`
- Modify: `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Add: `services/control-plane-swift/Tests/ControlPlaneTests/MCPToolCatalogTests.swift`

- [x] Define typed control-plane snapshot fields for effective MCP configuration, enabled tool sources, and resolved tool count.
- [x] Implement a repository-owned MCP configuration loader and normalization model in `MCPToolCatalog.swift`, including deterministic source IDs, enabled flags, namespace normalization, and invalid-entry rejection.
- [x] Publish the effective MCP state through `ControlPlaneService` snapshot and handshake paths so later UI and API surfaces can inspect the same source of truth.
- [x] Add failing and then passing control-plane tests for config load success, invalid-config isolation, and snapshot serialization.
- [x] Regenerate protocol outputs with `make proto`.

## Task 2: Wire MCP Auto-Injection Into Request Shaping And Streaming Metadata

**Files:**
- Modify: `services/control-plane-swift/Sources/Requests/ToolParserRegistry.swift`
- Modify: `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`
- Modify: `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
- Add: `tests/integration/test_mcp_tool_injection.py`
- Add: `tests/test_m9_mcp_smoke.py`

- [x] Extend the tool-parser resolution path so request shaping can merge built-in tool-parser state with effective MCP tool namespaces and their source identity.
- [x] Auto-inject enabled MCP tools only when the request, model policy, and parser mode support structured tools; preserve explicit opt-out and duplicate suppression.
- [x] Surface MCP-derived tool metadata in request ext fields and streamed tool-call payload metadata so external consumers can tell whether a tool came from `request`, `model`, or `mcp`.
- [x] Add failing and then passing unit and integration tests for auto-injection success, disabled-source opt-out, duplicate suppression, and invalid parser-mode rejection.
- [x] Record `mcp.tool_injection_success_rate` and `mcp.configured_tool_count` in the touched scope.

## Task 3: Add Runbook And Deterministic Smoke Coverage

**Files:**
- Add: `scripts/m9_mcp_smoke.py`
- Add: `docs/runbooks/mcp-tooling.md`
- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Add a deterministic smoke script that loads a fixture MCP config, asks the handler for tool-enabled request translation, and emits machine-readable success and failure detail.
- [x] Document the supported MCP config shape, activation path, failure modes, and smoke command in repository-owned runbooks.
- [x] Capture an explicit metrics report for the changed scope.

## Verification And Commit Gate

- [x] Run targeted verification:
  - `make proto`
    - Result: `./scripts/proto_gen.sh`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'environmentLoadingReturnsEmptyCatalogWhenConfigPathIsMissingOrBlank|configLoadingNormalizesSourcesAndParserMode|configLoadingFallsBackToAnEmptyCatalogForInvalidFiles|mcpToolCatalogsAutoInjectNamespacesAndDefaultParserSelection|mcpToolCatalogsMergeIntoModelDefaultsWithoutLosingModelParserMode|mcpToolCatalogsPreserveExplicitTextParserOptOut|mcpToolCatalogsDoNotCreateParserSelectionWhenNoEnabledNamespacesRemain|handshakeExposesMCPToolCatalogStateInFeaturesAndSnapshot|startChatAutoInjectsMCPToolMetadataIntoWorkerRequests|postResponsesAutoInjectsMCPToolNamespacesAndSourceIDs|toolFramesIncludeMCPSourceIdentifiersWhenPresent'`
    - Result: `11 tests in 5 suites passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_mcp_tool_injection.py tests/test_m9_mcp_smoke.py -q`
    - Result: `4 passed in 10.66s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_mcp_smoke.py --json`
    - Result: all checks `true`; metrics recorded `mcp.config_load_latency_ms=1.443028450012207`, `mcp.configured_tool_count=2`, `mcp.disabled_tool_source_count=1`, `mcp.refused_tool_count=1`, `mcp.tool_injection_count=1`, `mcp.tool_injection_success_rate=1`
- [x] Measure changed-line coverage for the touched Swift and integration scope and confirm coverage is at least `95%`.
  - Swift changed-line coverage: `100.00% (555/555)` across the touched Swift source and test scope.
  - Python changed-line coverage: `100.00% (118/118)` across `tests/integration/test_mcp_tool_injection.py`, `scripts/m9_mcp_smoke.py`, and `tests/test_m9_mcp_smoke.py`.
  - Generated protobuf artifacts under `packages/protocol/` were excluded from hand-written coverage accounting.
- [x] Record the changed-scope metrics report for `mcp.tool_injection_success_rate`, `mcp.config_load_latency_ms`, `mcp.configured_tool_count`, `mcp.disabled_tool_source_count`, and `mcp.refused_tool_count`.
  - `mcp.tool_injection_success_rate = 1`
  - `mcp.config_load_latency_ms = 1.443028450012207`
  - `mcp.configured_tool_count = 2`
  - `mcp.disabled_tool_source_count = 1`
  - `mcp.refused_tool_count = 1`
- [x] Commit M9.1 with the MCP catalog, request-shaping, streaming metadata, runbook, smoke coverage, and this execution record.
