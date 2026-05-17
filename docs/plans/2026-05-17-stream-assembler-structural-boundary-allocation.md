# Stream Assembler Structural Boundary Allocation Slice

## Goal

Reduce per-drain allocation overhead in the Python request stream assembler's structural-boundary lookup path without changing parsing semantics.

## Scope

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`

## Registered Probe

The affected file is covered by the PR-scoped registered probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. That entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and runs on `ubuntu-latest`.

## Implementation Plan

1. Preserve behavior around enabled structural boundaries with focused tests for `_next_structural_tag_after()`.
2. Replace short-lived list construction in `_earliest_structural_tag()` and `_next_structural_tag_after()` with direct candidate comparisons.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use the PR-scoped performance workflow as the merge gate for the registered probe report.

## Metrics

Primary metric: `stream-assembler-parser-mode-cache` `elapsed_ms_mean` (lower is better).
