# Trajectory provenance immutable-first copy slice

This Python-only performance slice is limited to `worker.trajectory_provenance._copy_trajectory_provenance_value`.

## Scope

The helper recursively copies JSON-like trajectory provenance containers before they are attached to training, adapter, and evaluation payloads. The hot path is leaf-heavy: most recursive visits are immutable JSON scalars rather than containers.

## Registered probe

The affected path is covered by the registered PR-scoped probe `trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. Its command-json probe compares the deep-copy baseline against the optimized provenance copier and reports elapsed time, peak bytes, speedup, and copied component count.

## Implementation plan

1. Preserve the existing dict/list/tuple recursive copy behavior and custom mutable fallback behavior.
2. Check exact immutable JSON scalar types before exact container types so recursive scalar leaves return before the container comparisons.
3. Verify with the probe's focused pytest command, changed-scope coverage command, and local registered probe on Linux.
4. Use PR-scoped performance CI as the merge gate.

## Metrics

Target metric: lower `optimized_elapsed_ms_mean` and positive `speedup` in `trajectory-provenance-copy-elision` while preserving `component_count`.
