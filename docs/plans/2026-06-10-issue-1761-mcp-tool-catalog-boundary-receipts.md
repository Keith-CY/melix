# Issue 1761 MCP Tool Catalog Boundary Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Record untrusted-context boundary receipts when MCP tool catalog
sources are auto-injected into worker request metadata.

**Architecture:** MCP tool catalogs are local skill/tool context and must be
treated as untrusted prompt-adjacent data. The control-plane translator will
attach request-local, redacted receipt evidence for the injected MCP source IDs
without copying tool namespaces, configuration paths, schemas, or prompt text.

**Tech Stack:** Swift control-plane request translation, Swift Testing,
`ExecutionMetadata.ext`, canonical JSON receipt evidence.

---

## Scope

This slice covers:

- MCP tool catalog source IDs that `TextRequestShaper` auto-injects through a
  `ToolParserSelection`.
- A Swift receipt helper that emits `melix.untrusted_context_receipt.v1`
  evidence under MCP-specific `ExecutionMetadata.ext` keys.
- Focused Swift tests proving that receipts are attached and remain redacted.
- Runtime contract documentation for the new MCP receipt keys.

This slice does not change MCP catalog loading, tool namespace normalization,
tool schema exposure, parser selection behavior, Python worker parsing, or live
MCP execution.

## Best End-State Architecture

MCP tools, agent skills, retrieved memories, retrieved documents, tool output,
and background continuations all cross an explicit untrusted-context boundary
before they influence model prompts or prompt-adjacent execution metadata.
Request translation should keep the already-redacted catalog source IDs as
metadata, attach a machine-readable receipt for each source, and avoid copying
the raw tool catalog into receipt JSON.

The receipt helper belongs beside the existing prompt-context receipt helpers
in `services/control-plane-swift/Sources/Requests`. It should be deterministic,
small, and independent from `MCPToolCatalog` loading so it records only the
source IDs that were actually selected by `TextRequestShaper`.

## Performance Probes And Metrics

The changed path creates one small dictionary per injected MCP source ID and
serializes one sorted JSON array. Runtime cost is linear in enabled MCP source
count and does not add filesystem reads, network calls, model inference,
scheduler work, or tool schema traversal.

Verification must include:

- focused red/green Swift test for MCP boundary receipt attachment;
- adjacent `ToolParserRegistryTests`;
- changed-line coverage for the Swift files touched by this slice with at
  least 95 percent coverage, or an explicit scoped coverage report if the
  changed lines are exercised by package coverage;
- full local pre-commit gate before commit on this host;
- PR performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

### Task 1: Add The Failing Translator Test

**Files:**

- Modify:
  `services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift`

- [ ] **Step 1: Add a Swift Testing case that translates a request with an MCP
      catalog containing enabled `filesystem` and `math` sources.**

The test must assert:

- `melix.mcp.source_ids = filesystem,math`;
- `melix.mcp.prompt_context.receipt_schema =
  melix.untrusted_context_receipt.v1`;
- `melix.mcp.prompt_context.receipt_count = 2`;
- receipt `source_id` values are `filesystem` and `math`;
- receipt `source_type = skill`;
- receipt `source_field = mcp_tool_catalog`;
- receipt `message_role = user`;
- receipt `policy = data_only`;
- receipt `included = true`;
- receipt `owner_scope_checked = false`;
- receipt JSON omits the MCP config path and tool namespaces.

- [ ] **Step 2: Run the focused test and verify it fails because the MCP receipt
      ext fields are absent.**

```bash
xcrun swift test --package-path services/control-plane-swift --filter ToolParserRegistryTests/translatedMCPToolCatalogsAttachSkillPromptContextReceipts
```

Expected: fail at the `melix.mcp.prompt_context.receipts_json` requirement.

### Task 2: Implement The MCP Receipt Helper

**Files:**

- Create:
  `services/control-plane-swift/Sources/Requests/MCPPromptContextBoundaryReceipt.swift`
- Modify:
  `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`

- [ ] **Step 1: Add `MCPPromptContextBoundaryReceipts` with deterministic JSON
      output.**

The helper must:

- accept `requestID` and selected `sourceIDs`;
- emit no ext fields when `sourceIDs` is empty;
- create `segment_id = <requestID>:mcp-source-<index>`;
- set `source_type = skill`;
- set `source_field = mcp_tool_catalog`;
- set `message_role = user`;
- set `trust_level = untrusted`;
- set `policy = data_only`;
- set `boundary_checked = true`;
- set `included = true`;
- set `owner_scope_checked = false`;
- use skill-specific reason and corrective-action text;
- serialize sorted-key JSON.

- [ ] **Step 2: Merge the helper's ext fields when
      `ChatRequestTranslator.translate` writes `melix.mcp.source_ids`.**

The translator should use the selected `toolParser.mcpSourceIDs`, not raw
catalog sources, so disabled and refused sources never receive admitted
receipts.

- [ ] **Step 3: Run the focused test and verify it passes.**

```bash
xcrun swift test --package-path services/control-plane-swift --filter ToolParserRegistryTests/translatedMCPToolCatalogsAttachSkillPromptContextReceipts
```

### Task 3: Document The Runtime Contract

**Files:**

- Modify: `docs/unified-agentic-tool-runtime-contract.md`

- [ ] **Step 1: Add the MCP-specific receipt keys to the untrusted prompt
      context contract.**

Document:

- `melix.mcp.prompt_context.receipt_schema`;
- `melix.mcp.prompt_context.receipt_count`;
- `melix.mcp.prompt_context.receipts_json`;
- one admitted receipt per selected MCP source ID;
- receipts use `source_type = skill` and `source_field = mcp_tool_catalog`;
- receipts omit config paths, tool namespaces, tool schemas, and private prompt
  text.

- [ ] **Step 2: Run adjacent Swift tests.**

```bash
xcrun swift test --package-path services/control-plane-swift --filter ToolParserRegistryTests
```

### Task 4: Verify, Commit, And Open The PR

**Files:**

- Verify all touched files.

- [ ] **Step 1: Run formatting and diff checks.**

```bash
git diff --check
```

- [ ] **Step 2: Run scoped coverage and metrics.**

Use the repository's changed-line or package coverage tooling for the touched
Swift request path. The changed scope must report at least 95 percent coverage,
or the PR evidence must explain why the scope is not currently measurable and
include the strongest available package coverage output.

- [ ] **Step 3: Run the full local pre-commit gate.**

```bash
.githooks/pre-commit
```

- [ ] **Step 4: Commit a focused change.**

```bash
git add services/control-plane-swift/Sources/Requests/MCPPromptContextBoundaryReceipt.swift \
  services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift \
  services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift \
  docs/unified-agentic-tool-runtime-contract.md \
  docs/plans/2026-06-10-issue-1761-mcp-tool-catalog-boundary-receipts.md
git commit -m "Add MCP catalog boundary receipts"
```

- [ ] **Step 5: Open a PR using the repository template headings exactly, then
      wait for CI, review, and the performance report.**

The PR must not merge until review threads are resolved, CI is green, the
branch is current with `origin/main`, and the performance report status is
`ok` with zero regressions.

## Success Criteria

- MCP tool catalog source IDs receive redacted untrusted-context receipt
  evidence when they are injected into worker request metadata.
- Receipt JSON contains source metadata and policy only, not config paths, tool
  namespaces, tool schemas, raw tool payloads, or private prompt text.
- Existing MCP parser-selection behavior is unchanged.
- Local verification, remote CI, code review, and PR performance report are all
  acceptable before squash merge.
