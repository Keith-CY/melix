# Trajectory Manifest Local Bindings

## Scope

This Python-only performance slice is limited to `load_trajectory_provenance_from_snapshot_manifest()` and its manifest-to-provenance helper in `services/mlx-worker-python/worker/trajectory_provenance.py`.

The hot path repeatedly reads trajectory snapshot manifests during dataset and LoRA provenance propagation. The existing registered probe `trajectory-manifest-json-load` already covers the affected path in `infra/perf/pr_scoped_probes.json` and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Plan

1. Preserve behavior with the existing trajectory provenance tests and PR-scoped probe smoke test.
2. Keep the optimization minimal: reduce repeated global/member lookups in manifest extraction by binding optional field metadata and provenance assignment locally while leaving copy semantics unchanged.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use the PR-scoped performance GitHub Actions report as the merge gate after push.

## Verification Notes

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
