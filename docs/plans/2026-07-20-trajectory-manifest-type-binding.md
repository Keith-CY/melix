# Trajectory manifest type binding performance slice

## Scope

This Python-only performance slice is limited to the clean manifest fast paths in `services/mlx-worker-python/worker/trajectory_provenance.py`, specifically the string type checks used while loading agentic trajectory snapshot manifests.

The existing implementation already reads manifest JSON as bytes and bypasses nested copy normalization for the direct load path. This slice keeps that behavior and only binds the module-level `_TYPE` helper once per fast path before repeated exact string type checks.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the trajectory manifest loader and probe script.

## Optimization plan

1. Preserve the existing clean-manifest fast path and fallback behavior.
2. Bind `_TYPE` once in `_fast_trajectory_provenance_from_snapshot_manifest(...)` and in the direct `load_trajectory_provenance_from_snapshot_manifest(...)` fast path.
3. Reuse the local binding for required/defaultable string field checks instead of repeated global `type` lookups.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate.

## Validation notes

This slice is locally verifiable on Linux. No Swift runtime effect is claimed.
