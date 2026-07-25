# Stream Marker Prefix Endswith Slice

## Scope

This Python-only performance slice is limited to the stream assembler marker-prefix
suffix helper used while holding incomplete reasoning close markers.

Affected implementation path:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`

The affected path is covered by the registered PR-scoped performance probe
`stream-assembler-structural-prefix-cache` in
`infra/perf/pr_scoped_probes.json`. This slice extends that probe with a
`close_marker_prefix_elapsed_ms_mean` metric so the close-marker helper changed
here is measured alongside the existing structural-prefix metrics.

## Plan

1. Preserve existing structural-prefix behavior with focused stream assembler
   regression tests.
2. Replace per-iteration text suffix slicing in
   `_longest_marker_prefix_suffix(...)` with marker-prefix `endswith(...)`
   checks, returning the same matched marker prefix.
3. Extend `scripts/stream_assembler_structural_prefix_probe.py` and the registry
   metrics so local and PR-scoped CI report the close-marker helper path.
4. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux before PR creation. GitHub Actions remains
   the merge gate for the registered PR-scoped performance report.

## Metrics

Primary metric:

- `close_marker_prefix_elapsed_ms_mean` — lower is better.

Guard metrics retained from the existing probe:

- `elapsed_ms_mean`
- `partial_suffix_elapsed_ms_mean`
- `long_literal_suffix_elapsed_ms_mean`
- `prefix_identity_hits`

## Validation Boundary

This slice changes Python code only and is locally verifiable on Linux. No Swift
runtime effect is claimed.
