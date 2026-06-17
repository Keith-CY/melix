# Metrics Snapshot Runtime Pattern Bounds

This Python-only performance slice is limited to `discover_latest_metrics_path(...)` in `scripts/melix_metrics_snapshot.py`.

## Scope

The runtime metrics snapshot discovery path scans the Melix runtime directory for source-specific metrics JSON files. The registered runtime patterns currently use zero or one `*` wildcard, so the hot loop can precompute the exact-name or prefix/suffix bounds once per discovery call instead of dispatching through `_matches_runtime_pattern(...)` for every directory entry.

Behavior remains equivalent:

- exact patterns still require the complete file name;
- single-wildcard patterns still require matching prefix and suffix;
- multi-wildcard patterns still fall back to `_matches_runtime_pattern(...)` and `fnmatch` semantics;
- only matching regular files are considered for newest-mtime selection.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `melix-metrics-snapshot-runtime-scandir` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/melix_metrics_snapshot.py`
- `scripts/melix_metrics_snapshot_discovery_probe.py`
- `tests/test_melix_metrics_snapshot.py`
- PR-scoped performance registry selection tests

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe result in CI.
