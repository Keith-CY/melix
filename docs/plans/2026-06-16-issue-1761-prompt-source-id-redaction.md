# Issue 1761 Prompt Source ID Receipt Redaction

## Goal

Ensure generic prompt-context boundary receipts do not expose raw source
identifiers that look like local paths, URLs, non-public identifiers, or long
store keys. The receipt should keep short public identifiers readable while
hashing non-public values into stable symbolic IDs.

## Scope

This slice is limited to Swift request translation receipt metadata:

- redact `PromptContextBoundaryReceipts` `source_id` values when message names or
  Harmony recipients look non-public;
- keep short public source IDs such as `rag_doc-17`, `skill-repo-search`, and
  `functions.get_weather` stable;
- share the source ID classification and hashing rules with MCP prompt-context
  receipt redaction while preserving MCP's existing `mcp-source:<hash>` prefix;
- preserve receipt schema, count, segment ordering, source type classification,
  and data-only policy fields.

Out of scope:

- changing normalized message content, roles, names, or Harmony execution
  metadata;
- changing `melix.mcp.source_ids`, SSE diagnostics, or MCP catalog loading;
- adding new retrieval, skill, memory, or workflow stores.

## Performance Probes And Metrics

The changed path adds a small identifier classification check and a SHA-256 hash
only when prompt-context receipt source IDs are attached. It does not change
prompt text assembly, worker scheduling, model execution, or requests without
receipt source IDs.

Verification must include:

- focused Swift tests for `ToolParserRegistryTests`;
- changed-scope Swift coverage for the touched helper/tests, or a documented
  coverage command failure if the local coverage tool cannot measure this scope;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required local gate before PR.

## Implementation Steps

1. Add a failing Swift test proving generic prompt-context receipt source IDs
   hash path-like, URL-like, very long, and non-ASCII message names without raw
   material in receipt JSON.
2. Introduce a shared deterministic prompt-context source ID redactor.
3. Wire `PromptContextBoundaryReceipts` through the redactor with a
   `prompt-source` prefix.
4. Move `MCPPromptContextBoundaryReceipts` to the shared redactor while
   preserving its `mcp-source` prefix and existing public-ID behavior.
5. Update the unified runtime contract and run focused verification.

## Success Criteria

- Generic prompt-context receipts preserve public source IDs.
- Generic prompt-context receipts replace path-like, URL-like, very long, or
  non-ASCII source IDs with `prompt-source:<sha256-prefix>`.
- MCP prompt-context receipts continue replacing non-public source IDs with
  `mcp-source:<sha256-prefix>`.
- Receipt JSON does not include local paths, URLs, prompt bodies, tool output,
  or raw private source identifiers.
