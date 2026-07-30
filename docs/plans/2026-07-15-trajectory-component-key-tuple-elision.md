# Trajectory Component Key Tuple Elision

## Scope

This Python-only performance slice is limited to the component-dictionary fast
path in `worker.trajectory_provenance._copy_trajectory_provenance_value()`.
The behavior remains a JSON-container copy: immutable scalar fields are copied
into a new component dictionary, tuple labels with immutable values are reused,
and mutable labels continue to fall back to recursive copying.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for this Python worker path.

## Optimization plan

1. Keep the existing component fast-path guard and behavior parity tests.
2. Replace the tuple-of-keys materialization (`tuple(value) == ...`) with direct
   keyed extraction under the existing `len(value) == 4` guard.
3. Remove the now-unused component-key tuple constant.
4. Validate locally on Linux with the registered focused tests, changed-scope
   coverage command, and registered probe before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Metrics target

The registered probe should show lower `optimized_elapsed_ms_mean` /
`elapsed_ms_mean` for the component-copy workload without increasing mutable
copy regressions. Peak bytes should remain at or below the previous local probe
range because the hot path no longer allocates a tuple only to compare key order.
The scalar-list/scalar-dict sidecar speedup ratios are informational controls;
their elapsed-time metrics remain the gated checks for those unrelated paths so
ratio noise cannot mask the component-dictionary signal.

## Validation boundary

This is Python-only and locally verifiable on Linux. GitHub Actions remains the
required registered PR-scoped probe validation source for merge.
