# Stream marker prefix precompute slice

## Scope

This Python-only performance slice is limited to `RequestStreamAssembler._longest_marker_prefix_suffix()` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

The helper is exercised while preserving reasoning or channel tails that end with a partial close marker, for example `</thi` before the next streamed chunk completes `</think>`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports `close_marker_prefix_elapsed_ms_mean` for this exact close-marker prefix path.

## Plan

1. Keep the close-marker prefix matching semantics unchanged for built-in markers and unknown custom markers.
2. Precompute built-in close-marker prefixes once on the class instead of slicing the same marker strings for every helper call.
3. Use direct built-in marker branches in the hot helper so repeated close-marker checks reuse the named prefix tuples without a dictionary lookup; preserve the tuple-building fallback for unknown custom markers.
4. Add focused regression coverage proving built-in marker prefix results reuse the precomputed prefix strings while the fallback path still handles unknown markers.
5. Run the focused tests, changed-scope coverage, and the registered structural-prefix probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.

## Success criteria

- Focused stream assembler tests pass.
- Changed-scope coverage remains at least 95 percent for the touched scope.
- The local registered probe shows lower `close_marker_prefix_elapsed_ms_mean` for the close-marker prefix workload without regressing behavior.
