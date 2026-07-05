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

## 2026-06-30 follow-up slice: skip configured-source runtime scan

This Python-only follow-up keeps the same registered
`melix-metrics-snapshot-runtime-scandir` probe and narrows to
`discover_latest_metrics_paths(...)`. When `resolve_source_paths(...)` has already
resolved every source from explicit arguments or environment variables, the
batched runtime discovery call receives an empty source tuple. The helper now
returns that empty result immediately instead of scanning the runtime directory
and testing entries that cannot match any unresolved source.

The behavior contract remains unchanged: argument and environment precedence are
preserved, partially unresolved calls still perform one runtime scan, and missing
runtime directories still return unresolved source paths without raising.

## 2026-07-02 follow-up slice: bind latest mtime lookup

This Python-only follow-up keeps the same registered
`melix-metrics-snapshot-runtime-scandir` probe and narrows to the hot per-entry
update path in `discover_latest_metrics_paths(...)`. The implementation binds the
latest-mtime dictionary lookup once before the scan loop, matching the existing
bound setter pattern and reducing repeated method resolution while preserving the
single-scan runtime discovery behavior.

The behavior contract remains unchanged: exact, prefix/suffix, empty-prefix, and
multi-wildcard runtime pattern matches still select the newest regular file per
source, and configured sources still bypass runtime scanning.

## 2026-07-03 probe calibration slice: configured-path noise floor

The rejected 2026-07-03 index-backed latest tracking slice showed that the
registered `melix-metrics-snapshot-runtime-scandir` probe's configured-source
metrics are too small to gate by percentage alone. The configured path bypasses
runtime discovery entirely and normally runs in roughly 0.02 ms, so sub-0.01 ms
host jitter can appear as a large percentage regression while the measured
runtime directory scan remains neutral or improved.

This Python/probe-only calibration keeps the existing probe, test command,
coverage command, and runtime discovery metrics. It adds a 0.01 ms absolute
warning floor to `configured_elapsed_ms_mean` and `configured_elapsed_ms_min` so
future behavior slices are gated on meaningful configured-path regressions rather
than measurement noise. The behavior contract remains unchanged: configured
sources still bypass runtime scanning, and runtime-scan `elapsed_ms_*` metrics
remain percentage-gated.

## 2026-07-05 follow-up slice: indexed latest-path tracking

This Python-only follow-up keeps the same registered
`melix-metrics-snapshot-runtime-scandir` probe and narrows to the hot latest-file
tracking structures inside `discover_latest_metrics_paths(...)`. The runtime
source names are now mapped to compact integer indexes before the directory scan,
so the per-entry path updates use list indexing instead of repeated source-name
dictionary get/set operations.

The behavior contract remains unchanged: exact, prefix/suffix, empty-prefix, and
multi-wildcard runtime pattern matches still select the newest regular file per
source; configured sources still bypass runtime scanning; and only the final
winning path for each source is materialized as a `Path`.
