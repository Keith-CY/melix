# PR-Scoped Performance Registry Scope-Stat Elision Plan

## Goal

Reduce redundant registry-file metadata checks in the PR-scoped performance scope loader by ensuring repeated `build_scope_report(...)` calls for an unchanged registry do not re-enter the direct registry loader's extra `stat()` path.

## Linux-Only Constraint

This slice is Python-only CI/performance infrastructure under `services/mlx-worker-python`. It is fully verifiable on Linux without macOS or Swift execution.

## Touched Files

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Proposed Change

1. Reuse the existing parsed-registry cache when the scope-specific cached loader is called with unchanged file metadata.
2. Parse and populate the cache through one shared helper so direct registry loads and scope-based registry loads preserve the same `ProbeDefinition` output.
3. Add a focused regression test that proves two repeated `build_scope_report(...)` calls only `stat()` the registry path once per call, not once in the scope wrapper plus again in the direct loader.
4. Update the existing `pr-scoped-performance-registry-cache` probe's focused test and coverage commands so hosted PR-scoped CI exercises the new regression test.

## Performance Probe

Probe ID: `pr-scoped-performance-registry-cache`

Metrics:
- `load_probe_registry_ms_mean` (lower is better)
- `cold_load_probe_registry_ms_mean` (lower is better)
- `build_scope_report_ms_mean` (lower is better)

## Success Metrics

- No behavior regression in scope selection, cache invalidation, or probe dispatch tests.
- Changed-scope automated coverage >= 95%.
- Local probe shows lower `build_scope_report_ms_mean` versus `origin/main`.

## Verification Commands

- Focused pytest for the registry-cache probe tests, including the new repeated-scope-load regression test.
- `coverage run -m pytest ...` plus `scripts/changed_scope_coverage.py` for changed executable lines.
- Local base-vs-head probe comparison for `pr-scoped-performance-registry-cache`.
- `git diff --check`.
