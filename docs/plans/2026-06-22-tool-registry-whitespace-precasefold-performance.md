# Tool Registry Whitespace Pre-Casefold Performance Slice

## Context

The agentic tool selector scans the current user turn for keyword hints when vector selection is unavailable. Whitespace-only turns cannot match any tool keyword, but the selector previously casefolded the string before checking `isspace()`, allocating and scanning text that can be rejected directly.

## Slice

Move the whitespace-only guard in `_keyword_tool_matches()` before `casefold()` so empty/blank turns return the fallback local-compute selection without allocating a normalized string.

## Probe Coverage

The existing registered PR-scoped probe `tool-registry-select-name-index-cache` covers `services/mlx-worker-python/worker/runtime/tool_registry.py` and runs focused tool-registry tests, coverage, and `scripts/tool_registry_select_probe.py`.

This slice extends that probe with:

- `whitespace_turn_planning_elapsed_ms_mean` (`lower_is_better`)
- `whitespace_turn_selected_schema_bytes_mean` (`informational`)

## Verification Plan

- Focused regression test: `test_agentic_tool_selection_whitespace_turn_skips_casefold`.
- Changed-scope coverage through the registered probe coverage command.
- Registered local probe run on Linux for old/new timing comparison.
- GitHub Actions PR-scoped performance report before merge.

## Expected Outcome

Whitespace-only selector planning should avoid `casefold()` and improve the registered whitespace-turn probe metric while preserving the same fallback selection behavior.
