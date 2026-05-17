# Stream Assembler Next Boundary Marker Fast Path

## Goal

Reduce repeated structural-boundary scans in `RequestStreamAssembler._next_structural_tag_after(...)` when a pipe-channel body has no further markup after the current body start.

## Scope

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`

## Registered Probe

The affected runtime file is covered by registered PR-scoped stream assembler probes in `infra/perf/pr_scoped_probes.json`, including `stream-assembler-parser-mode-cache`. Those entries include focused `test_command`, `coverage_command`, and `probe_command` fields and run on `ubuntu-latest`.

## Implementation Plan

1. Add a focused regression test for `_next_structural_tag_after(...)` returning `-1` when no `<` marker remains after the requested start offset.
2. Add a single-character marker precheck before the more specific structural tag searches.
3. Run focused tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use the PR-scoped performance workflow report as the merge gate.

## Metrics

Primary registered metric: `stream-assembler-parser-mode-cache` `elapsed_ms_mean` (lower is better). Local acceptance also records a focused micro-probe for `_next_structural_tag_after(...)` on no-boundary pipe-channel tails because this slice targets that helper directly.
