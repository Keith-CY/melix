# Metrics snapshot final path materialization slice

## Scope

This Python-only performance slice is limited to `discover_latest_metrics_path()`
in `scripts/melix_metrics_snapshot.py`. Runtime metrics discovery still performs
one `os.scandir()` pass over the runtime directory and selects the newest metrics
file by modification time.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`melix-metrics-snapshot-runtime-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `scripts/melix_metrics_snapshot.py`
- `scripts/melix_metrics_snapshot_discovery_probe.py`
- `tests/test_melix_metrics_snapshot.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Implementation plan

Avoid materializing a `Path` object each time the current newest directory entry
changes during the scan. Keep the current best `DirEntry.path` string in the hot
loop and construct the returned `Path` only once after the scan completes.

## Follow-up slice: configured-source discovery elision

When all metrics sources are explicitly configured by CLI arguments or
environment variables, `resolve_source_paths()` has no runtime source names left
to discover. Skip the batched runtime-discovery helper entirely in that case so
the configured-source hot path avoids the extra empty dispatch/allocation while
preserving the existing no-`os.scandir()` behavior.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before opening the PR. GitHub Actions PR-scoped
performance remains the merge gate for the registered probe report.
