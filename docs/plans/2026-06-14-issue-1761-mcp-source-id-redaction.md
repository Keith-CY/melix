# Issue 1761 MCP Source ID Receipt Redaction

## Goal

Ensure MCP tool-catalog prompt-context receipts expose only redacted source
identifiers, while keeping the existing `melix.mcp.source_ids` execution
metadata unchanged for routing and stream diagnostics.

## Scope

This slice is limited to Swift request translation receipt metadata:

- redact MCP receipt `source_id` values when source identifiers look like
  paths, URLs, or other non-public identifiers;
- keep short public identifiers, such as `filesystem` and `math`, stable;
- keep `melix.mcp.source_ids` unchanged so tool-parser reconstruction remains
  backward compatible;
- preserve existing receipt schema, count, segment ordering, and data-only
  policy fields.

Out of scope:

- changing MCP catalog discovery, namespace normalization, or high-risk
  namespace refusal;
- changing SSE `mcp_source_ids` diagnostics;
- adding live MCP tool execution or MCP store ownership checks.

## Performance Probes And Metrics

The changed path adds a small identifier classification check and a SHA-256 hash
only for non-public source identifiers when MCP catalog receipt metadata is
attached. It does not change request prompt assembly, worker scheduling, model
execution, or default no-MCP requests.

Verification must include:

- focused Swift red/green tests for `ToolParserRegistryTests`;
- `git diff --check`;
- changed-scope coverage or an explicit Swift coverage note if the local
  command cannot produce line coverage for this single helper slice;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required local gate before PR if the pre-commit hook requires it.

## Implementation Steps

1. Add a failing Swift test proving non-public MCP source IDs are hashed in
   receipt JSON and raw path/URL material is absent.
2. Implement deterministic source ID redaction in
   `MCPPromptContextBoundaryReceipts`.
3. Keep the existing public-ID receipt tests green.
4. Run focused tests, coverage/metrics checks, and the required local gate
   before opening the PR.

## Success Criteria

- MCP prompt-context receipts still attach `source_type = skill`,
  `source_field = mcp_tool_catalog`, and data-only policy metadata.
- Public source IDs remain readable in receipts.
- Path-like, URL-like, very long, or delimiter-heavy source IDs are replaced by
  stable `mcp-source:<sha256-prefix>` values in receipt JSON.
- Receipt JSON does not include MCP config paths, namespaces, raw private source
  IDs, tool arguments, or prompt bodies.
