# Trajectory Manifest Path String Fast Path

## Scope

This Python performance slice is limited to `worker.trajectory_provenance` snapshot manifest loading.
It keeps trajectory provenance behavior unchanged while avoiding repeated `Path` stringification in the hot
manifest load path.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Implementation plan

1. Add a regression test proving the loader passes precomputed path text into the extraction helper.
2. Compute the manifest path string once after normalizing the input path.
3. Preserve the public helper behavior for direct `Path`, `str`, and mapping subclass inputs.
4. Run the focused registered probe commands locally on Linux and use PR-scoped performance CI as the merge gate.

## Success criteria

- Focused trajectory provenance tests pass.
- Changed-scope coverage for `worker.trajectory_provenance` remains at least 95%.
- The local registered probe reports a lower `new_mean_ms` than its baseline or an acceptable neutral delta.
- GitHub Actions and the registered PR-scoped performance workflow complete successfully before merge.
