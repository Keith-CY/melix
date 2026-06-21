# Trajectory manifest clean-text inline checks

This Python-only performance slice is limited to the clean normalized-manifest fast path in `worker.trajectory_provenance._fast_trajectory_provenance_from_snapshot_manifest()`.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

The current fast path validates five required exact-string manifest fields by calling `_is_clean_manifest_text()` repeatedly. This slice keeps the same fallback boundary but inlines the exact-string and leading/trailing whitespace checks in the hot path so normalized JSON manifests avoid per-field Python helper calls.

The fallback path remains responsible for missing fields, non-string values, whitespace-normalized values, dict subclasses, source aliases, and the public copy-preserving API.

## Verification

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered base-vs-head report.
