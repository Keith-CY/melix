# Metrics snapshot source discovery single-scan slice

## Scope

This Python-only performance slice is limited to runtime metrics source discovery in
`scripts/melix_metrics_snapshot.py`. The snapshot CLI still resolves explicit
arguments first, environment paths second, and runtime directory discovery last.
It does not change metrics payload parsing, freshness handling, CLI arguments, or
Swift/macOS runtime behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`melix-metrics-snapshot-runtime-scandir` in `infra/perf/pr_scoped_probes.json`.
This slice keeps the probe registered and updates its focused command coverage so
it exercises `resolve_source_paths(...)` across all runtime-backed sources.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/melix_metrics_snapshot.py`
- `scripts/melix_metrics_snapshot_discovery_probe.py`
- `tests/test_melix_metrics_snapshot.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Implementation plan

1. Add a batched runtime metrics discovery helper that scans the runtime
   directory once for all unresolved source names.
2. Bucket simple prefix/suffix runtime patterns by their first prefix character
   so the single directory scan avoids checking every source pattern for every
   directory entry.
3. Preserve the single-source `discover_latest_metrics_path(...)` API by routing
   it through the batched helper.
4. Update `resolve_source_paths(...)` to collect only sources not configured by
   argument or environment, then use one batched scan for those runtime candidates.
5. Add regression coverage proving mixed environment/runtime resolution performs
   one `os.scandir(...)` call and preserves source precedence.
6. Update the registered probe workload to measure the multi-source resolution
   path instead of only the single-source helper.

## Follow-up slice: lazy overlapping match materialization

The next focused Python slice keeps the same registered probe and runtime
metrics discovery boundary. It avoids creating a per-entry list for the common
case where a runtime file matches only one exact or prefix/suffix source pattern,
while still preserving overlapping exact, prefix, and multi-wildcard matches.
The behavior contract remains unchanged: a single runtime directory scan chooses
the newest matching file for each unresolved source.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before opening the PR. GitHub Actions PR-scoped
performance remains the merge gate for the registered probe report.
