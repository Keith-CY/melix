# Tool Registry Selection Append Helper Performance Slice

## Scope

This slice keeps agentic tool selection behavior unchanged while moving the hot
selection append checks out of the per-call nested closure in
`select_agentic_tools_for_turn`.

Affected paths:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`

## Motivation

`select_agentic_tools_for_turn` runs on every agentic planning turn. The prior
implementation rebuilt a nested `add_tool` closure for every call and used that
closure for always-available, vector, current-turn keyword, and context keyword
candidate insertion. Reusing a module-level helper removes that per-call closure
allocation while preserving the existing normalization, deduplication, capacity,
and built-in-name validation rules.

## Behavior Contract

- Always-available tools remain inserted first.
- Blank candidate names are ignored.
- Duplicate candidate names are ignored after normalization.
- Unknown candidate names are ignored.
- `max_selected_tools` is still enforced before optional vector or keyword
  candidates are appended.
- Vector selection still returns immediately when at least one vector hit is
  accepted.
- Keyword fallback behavior remains unchanged when vector selection is absent or
  produces no accepted hit.

## Registered Probe

The path is covered by the existing PR-scoped probe registry entry:

- `tool-registry-select-name-index-cache`
- `watch_globs` include `services/mlx-worker-python/worker/runtime/tool_registry.py`,
  `services/mlx-worker-python/tests/test_tool_registry.py`, and
  `scripts/tool_registry_select_probe.py`.
- The registry entry provides focused `test_command`, `coverage_command`, and
  `probe_command` values.

## Verification Plan

Run from the repository root with `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python"`:

1. Focused pytest for tool registry selection and the registered PR-scoped probe tests.
2. Changed-scope coverage for the touched Python/test/probe paths.
3. Registered local probe: `uv run --project services/mlx-worker-python python3 scripts/tool_registry_select_probe.py`.
4. Compare the probe output against a clean `origin/main` baseline worktree.

## Decision Criteria

Accept the slice only if focused tests and changed-scope coverage pass, and the
registered local probe shows an improvement in the primary selection timing while
any secondary metric regression remains within the registry warning threshold.
