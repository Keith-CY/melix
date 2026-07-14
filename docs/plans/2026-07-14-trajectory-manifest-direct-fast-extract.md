# Trajectory Manifest Direct Fast Extract

This Python-only performance slice is limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest()` for normalized agentic trajectory snapshot manifests loaded from JSON bytes.

## Registered Probe

The affected path is covered by the existing registered PR-scoped performance probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

Normalized manifest loads currently parse JSON bytes into an exact `dict`, then enter `_trajectory_provenance_from_snapshot_manifest()`, whose first branch immediately calls the clean-manifest fast extractor. This keeps behavior correct, but it spends an extra Python function frame and fallback setup on the hot path that already has the exact loaded `dict` and snapshot path text.

This slice keeps the clean-manifest extraction branch directly in `load_trajectory_provenance_from_snapshot_manifest()` when the decoded payload is an exact `dict`. If the inline fast branch rejects the manifest, the existing fallback extractor is still used, preserving whitespace cleanup, dict-subclass handling, non-trajectory behavior, and nested-copy semantics.

## Verification

Run the registered focused test command, changed-scope coverage command, and `trajectory-manifest-json-load` probe locally before pushing. Compare the probe output before and after the change; accept the slice only if the registered probe remains directionally improved or neutral with behavior tests passing.
