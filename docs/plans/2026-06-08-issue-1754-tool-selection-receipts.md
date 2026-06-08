# Issue 1754 Tool Selection Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, receipt-backed agentic tool selection slice that keeps always-available tools, consumes optional vector retrieval results, and falls back to keyword matching over the current turn plus recent context.

**Architecture:** Reuse the existing Python worker built-in tool registry as the source of truth. Add a small selector API in `worker.runtime.tool_registry` that returns a selected `ToolRegistry` plus a redacted receipt with source labels, dropped count, and schema-byte reduction evidence. Wire that selector into the deterministic agentic runtime so selected registries become the execution allowlist and the selection receipt is persisted in run evidence. This slice does not add a vector database; it accepts vector-selected tool IDs from a future retriever and makes unavailable-vector fallback deterministic now.

**Tech Stack:** Python 3.12, pytest, existing protobuf `ToolConfig`, existing built-in agentic tool registry.

---

## Scope

This slice covers issue #1754 acceptance criteria that can be implemented without introducing a vector store:

- preserve always-available diagnostic tools
- accept vector-selected tool IDs when an upstream retriever is available
- use deterministic keyword fallback when vector retrieval is unavailable
- use recent user context so short follow-up prompts still select the prior-domain tool
- emit a receipt with selected tool IDs, source labels, dropped count, retrieval status, fallback reason, and schema-byte reduction

Out of scope for this PR:

- embedding or vector index construction
- App, CLI, or model prompt assembly integration
- rewriting individual tool adapters

## Files

- Modify: `services/mlx-worker-python/worker/runtime/tool_registry.py`
- Modify: `services/mlx-worker-python/worker/runtime/agentic_tools.py`
- Modify: `services/mlx-worker-python/tests/test_tool_registry.py`
- Modify: `services/mlx-worker-python/tests/test_agentic_tools.py`
- Modify: `docs/unified-agentic-tool-runtime-contract.md`

## Tasks

### Task 1: Selection Receipt Tests

- [x] Add failing tests in `services/mlx-worker-python/tests/test_tool_registry.py` for:
  - vector-selected tools plus always-available tools
  - vector-unavailable keyword fallback
  - short follow-up prompt using recent context
  - no-keyword fallback receipt
- [x] Run focused pytest and confirm the new tests fail because the selector API is missing.

### Task 2: Selector Implementation

- [x] Add `ToolSelectionInput`, `ToolSelectionResult`, and a public `select_agentic_tools_for_turn()` helper in `tool_registry.py`.
- [x] Add built-in tool hint metadata and an always-available diagnostic tool policy.
- [x] Implement deterministic vector, keyword, context, and fallback ordering.
- [x] Emit `melix.agentic_tool_selection.v1` receipts without prompt text or secrets.
- [x] Run focused pytest and confirm the tests pass.

### Task 3: Contract Documentation and Metrics

- [x] Update `docs/unified-agentic-tool-runtime-contract.md` with the tool-selection receipt contract.
- [x] Run focused tests, changed-scope coverage, and an overhead probe or explicit metrics report for selector planning.
- [x] Commit the selector slice with verification and metrics evidence.

### Task 4: Deterministic Runtime Receipt Integration

- [x] Add failing runtime tests that pass `ToolSelectionInput` through `execute_agentic_tool_calls()`.
- [x] Use the selected registry as the deterministic runtime allowlist.
- [x] Persist `melix.agentic_tool_selection.v1` inside the existing run registry receipt without raw prompt text, private context, or tool arguments.
- [x] Verify dropped tools are rejected by the selected runtime registry.
- [x] Commit the runtime integration slice with verification and metrics evidence.

## Performance Probes

Success metrics for this slice:

- selection planning does not load models or make network calls
- selected schema bytes are lower than full built-in schema bytes for bounded selections
- focused selector tests complete in normal Python unit-test time

## Verification Evidence

- TDD red: `pytest -q services/mlx-worker-python/tests/test_tool_registry.py -q` failed during collection with missing `ToolSelectionInput`.
- Focused behavior tests: `63 passed in 0.06s`.
- Changed-line coverage: `TOTAL 96.19% 101/105`.
- Local selector planning probe with `MELIX_TOOL_REGISTRY_SELECT_ITERATIONS=2000` and `MELIX_TOOL_REGISTRY_SELECT_SAMPLES=2`: `selector_planning_elapsed_ms_mean=0.8312500140164047`, `selector_selected_schema_bytes_mean=565.85`.
- Runtime integration red: `pytest -q ...test_agentic_tool_runtime_records_selection_receipt_for_selected_registry ...test_agentic_tool_runtime_rejects_tool_dropped_by_selection` failed with `TypeError: execute_agentic_tool_calls() got an unexpected keyword argument 'tool_selection'`.
- Runtime integration green: `services/mlx-worker-python/tests/test_agentic_tools.py` passed with `59 passed in 0.07s`.
- Runtime focused tests and coverage: `122 passed in 0.26s`; changed-line coverage `TOTAL 100.00% 26/26`.
