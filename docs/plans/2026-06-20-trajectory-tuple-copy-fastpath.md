# Trajectory provenance tuple scalar copy fast path

## Scope

This Python performance slice is limited to the trajectory provenance copy helper in `services/mlx-worker-python/worker/trajectory_provenance.py`.

Registered PR-scoped probe: `trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries for the affected path.

## Root Cause

Trajectory provenance metrics can include tuple-valued scalar labels from in-memory callers. The copy helper already avoids recursive scalar copies for lists, but exact tuples are always rebuilt through a generator even when every item is JSON-immutable. That adds avoidable per-item Python calls and tuple allocation for an immutable container that can be safely reused.

## Plan

1. Add a tuple-specific helper that returns exact tuples unchanged when every item is JSON-immutable.
2. Preserve defensive copying for tuples that contain mutable or custom objects.
3. Extend focused tests to cover the scalar tuple fast path and nested mutable tuple fallback.
4. Extend the registered trajectory provenance copy-elision probe workload with tuple labels and keep the probe registry commands focused on this slice.
5. Treat the probe's synthetic `baseline_elapsed_ms_mean` as informational because it measures the embedded old-style comparison helper, while `optimized_elapsed_ms_mean`, `speedup`, and `peak_bytes_mean` remain the merge-gating head-path metrics.

## Validation

- Run the focused `trajectory-provenance-copy-elision` test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require at least 95% for `trajectory_provenance.py`.
- Run `scripts/trajectory_provenance_copy_elision_probe.py` locally on Linux and use GitHub Actions PR-scoped performance as the merge gate.
