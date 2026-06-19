# Trajectory Fast Manifest Binding Performance Slice

## Scope

This slice keeps the trajectory provenance behavior unchanged and narrows the
hot path inside `services/mlx-worker-python/worker/trajectory_provenance.py`.
The target is the clean JSON manifest fast path used by
`load_trajectory_provenance_from_snapshot_manifest` after reading a snapshot
`manifest.json` as bytes.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`.
That probe includes:

- focused tests via `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- changed-scope coverage for `worker.trajectory_provenance`
- probe command via `scripts/trajectory_manifest_json_load_probe.py`

## Implementation Plan

1. Preserve the existing bytes-based manifest load and clean-manifest fast path.
2. Bind repeated hot-loop helpers (`manifest.get` and clean-text predicate) to
   local variables inside `_fast_trajectory_provenance_from_snapshot_manifest`.
3. Run focused trajectory provenance tests, changed-scope coverage, and the
   registered trajectory manifest JSON probe locally on Linux.
4. Let the PR-scoped performance workflow validate the same registered probe in
   CI before merge.

## Linux Probe Notes

Pre-change local probe from the synced `origin/main` worktree:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT="$PWD" \
MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_SAMPLES=7 \
MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_ITERATIONS=3000 \
uv run --project services/mlx-worker-python python3 scripts/trajectory_manifest_json_load_probe.py

old_mean_ms=2253.113, new_mean_ms=1177.632, speedup=1.913x, delta_ms=-1075.481
```

Initial post-change local probe:

```text
old_mean_ms=2273.054, new_mean_ms=1167.748, speedup=1.947x, delta_ms=-1105.306
```

The authoritative merge gate remains the registered PR-scoped performance CI
report.
