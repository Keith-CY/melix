# Job Registry Restore Sort Elision

## Scope

- Affected path: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Supporting tests: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- Existing PR-scoped probe: `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`
- Probe support path: `scripts/job_registry_derived_model_probe.py`
- Constraint: Linux-only local verification; no macOS/Swift validation is available in this cron run.

## Goal

Remove redundant restore-time sorting in `ModelOpsJobRegistry` while preserving manifest restore ordering and behavior.

## Why this slice

`_collect_restore_manifest_paths()` already sorts each operation-specific manifest path list before returning it. `_restore_manifest_jobs()` then calls `sorted(manifest_paths)` again, repeating work on already ordered inputs during cold restore from disk.

## Implementation

1. Keep `_collect_restore_manifest_paths()` as the single owner of restore manifest ordering.
2. Remove the duplicate sort inside `_restore_manifest_jobs()`.
3. Add a focused regression test that fails if `_restore_manifest_jobs()` falls back to `sorted(...)` for already ordered inputs.
4. Preserve all restore semantics and job ordering.

## Verification Plan

Run the registered probe's Linux-safe local verification path:

1. Focused tests covering `job_registry.py` plus the probe-registration smoke tests.
2. Changed-scope coverage via `coverage run`, `coverage json`, and `scripts/changed_scope_coverage.py`.
3. Explicit base-vs-head probe through `scripts/pr_scoped_performance_run.py` for `job-registry-derived-model-single-pass`.
4. `git diff --check` before commit.

## Success Criteria

- Focused tests pass.
- Changed executable scope coverage is at least 95%.
- The registered probe shows equal or better restore-path performance versus `origin/main`.
- No behavior regressions in restored job ordering or manifest handling.
