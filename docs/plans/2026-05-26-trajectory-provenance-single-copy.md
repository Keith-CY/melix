# Trajectory provenance single-copy normalization

## Scope

This Python performance slice is limited to trajectory snapshot manifest provenance extraction in `services/mlx-worker-python/worker/trajectory_provenance.py`.

`trajectory_provenance_from_snapshot_manifest(...)` used to copy nested JSON provenance fields while building the intermediate `provenance` mapping, then `normalize_trajectory_provenance(...)` copied the same nested JSON containers again before returning the public payload. The slice keeps the returned payload detached from the source manifest, but lets normalization perform the single required deep copy.

## Registered probe

The affected path is covered by the registered PR-scoped probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and require at least 95% for the changed scope.
3. Run the registered `trajectory-manifest-json-load` probe locally with a base worktree from `origin/main` and this head worktree. The probe's `delta_ms` metric is informational for this slice because both old and new in-script JSON loading paths share the downstream provenance extractor; direct merge gating should use `new_mean_ms`, `speedup`, and peak-memory metrics.
4. Use the GitHub Actions PR-scoped performance workflow as the final merge gate before merging.

## Success criteria

- Snapshot manifest provenance behavior and nested-container detachment remain unchanged.
- The focused changed-scope coverage command reports at least 95% coverage for `trajectory_provenance.py`.
- The registered probe shows lower `new_mean_ms` than the base-vs-head baseline for the manifest extraction workload.
