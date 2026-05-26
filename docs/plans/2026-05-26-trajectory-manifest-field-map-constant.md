# Trajectory manifest field-map constant

## Scope

This Python-only performance slice is limited to trajectory snapshot manifest
provenance extraction in
`services/mlx-worker-python/worker/trajectory_provenance.py`.

`trajectory_provenance_from_snapshot_manifest(...)` is called repeatedly by the
registered `trajectory-manifest-json-load` probe. The optional source-to-output
field mapping was previously rebuilt as a tuple literal on each call. This slice
hoists that immutable mapping to module scope so the hot path reuses the same
field-map object while preserving the returned provenance payload and detached
nested-container behavior.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`.

The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and require
   at least 95% coverage for `worker.trajectory_provenance`.
3. Run the registered `trajectory-manifest-json-load` probe locally before and
   after the change to compare `new_mean_ms`, peak bytes, and speedup.
4. Use the GitHub Actions PR-scoped performance workflow as the final merge gate
   before merging.

## Success criteria

- Snapshot manifest provenance field names and optional field behavior remain
  unchanged.
- Changed-scope coverage remains at least 95% for the touched worker module.
- The registered probe shows a neutral-or-better local direction and CI validates
  the registered base-vs-head probe report before merge.
