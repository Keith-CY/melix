# PR-Scoped Performance Registry Cache Plan

## Goal

Reduce repeated registry JSON parsing and file reads in the PR-scoped performance selector by caching parsed probe definitions for an unchanged registry file.

## Linux-Only Constraint

This slice targets Python-only CI/performance infrastructure under `services/mlx-worker-python`. It is fully verifiable on Linux without macOS or Swift execution.

## Touched Files

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Proposed Change

1. Add a small cache in `load_probe_registry()` keyed by the registry path plus file metadata sufficient to invalidate when the JSON file changes.
2. Keep output semantics unchanged: callers still receive the same tuple of `ProbeDefinition` values.
3. Register a dedicated PR-scoped performance probe for the registry-cache path so CI measures the touched helper directly.
4. Add focused tests for cache hit behavior, invalidation on file change, probe selection, and probe execution.

## Performance Probe

Probe ID: `pr-scoped-performance-registry-cache`

Measure repeated registry loading / scope selection on a stable registry file.

Metrics:
- `load_probe_registry_ms_mean` (lower is better)
- `build_scope_report_ms_mean` (lower is better)

The registry-cache timing metrics use absolute warning floors alongside percentage thresholds: 0.5 ms for hot load and scope selection, and 10 ms for cold load. The probe intentionally measures CI infrastructure paths whose absolute cost is small relative to the full workflow, and cold JSON load timing is sensitive to host file-cache state.

## Success Metrics

- No behavior regression in scope selection or probe execution tests.
- Changed-scope automated coverage >= 95%.
- Local probe shows lower mean time for repeated `load_probe_registry()` and/or `build_scope_report()` versus `origin/main`.

## Verification Commands

- Focused pytest for `test_pr_scoped_performance.py` nodes covering the cache and probe.
- `coverage run -m pytest ...` plus `scripts/changed_scope_coverage.py` for changed executable lines.
- Dedicated local base-vs-head probe command for `pr-scoped-performance-registry-cache`.
- `git diff --check`.
