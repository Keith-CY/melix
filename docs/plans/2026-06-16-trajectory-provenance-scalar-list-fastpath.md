# Trajectory provenance scalar-list copy fast path

## Scope

This Python-only performance slice is limited to `worker.trajectory_provenance._copy_trajectory_provenance_value`.
It preserves defensive copying for mutable containers while avoiding recursive helper calls for exact lists whose items are JSON-immutable scalars.

## Registered performance probe

The affected path is already covered by the registered PR-scoped probe `trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe measures `normalize_trajectory_provenance` on synthetic trajectory quality metrics with nested component labels and reports:

- `optimized_elapsed_ms_mean`
- `baseline_elapsed_ms_mean`
- `speedup`
- `optimized_peak_bytes_mean`

## Implementation plan

1. Add a narrow exact-list scalar fast path inside trajectory provenance copying.
2. Add regression coverage proving scalar-only lists are copied without recursive helper calls and mixed lists still deep-copy nested mutable values.
3. Run focused tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.
