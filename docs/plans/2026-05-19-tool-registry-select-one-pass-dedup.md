# Tool Registry Select One-pass Deduplication

Date: 2026-05-19

## Scope

This performance slice optimizes `ToolRegistry.select()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py` only.

## Problem

The select path preserves requested order, strips blank names, deduplicates
repeated names, validates missing entries, and then builds a selected registry.
The current implementation uses `dict.fromkeys(...)` over a generator to perform
trimming/filtering/deduplication before the missing-name scan. That creates an
intermediate dictionary for every selection call, even though the hot path only
needs an ordered list of distinct requested names.

## Plan

- Replace the `dict.fromkeys(...)` construction with a single explicit loop that
  strips, filters, deduplicates, and appends requested names.
- Keep the cached `_tool_by_name` lookup from the previous slice unchanged.
- Preserve unknown-name reporting order and selected-tool order.
- Add a focused regression test for blank-name filtering and deduplication.

## Registered probe

The affected path is already covered by the PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for this file, `test_tool_registry.py`, PR-scoped probe
selection tests, and `scripts/tool_registry_select_probe.py`.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command and require at least 95%
  changed-line coverage.
- Run `scripts/tool_registry_select_probe.py` before and after the change and
  compare `elapsed_ms_mean` while preserving `select_calls_mean` and checksum.
- Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
