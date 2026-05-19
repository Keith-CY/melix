# Job Registry Trimmed-ID Lookup Cache Slice

## Scope

This Python-only performance slice targets `ModelOpsJobRegistry.resolve_derived_model_target` for callers that pass a derived model id with surrounding whitespace and no manifest path.

## Registered probe

The affected path is covered by the existing PR-scoped probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/job_registry_derived_model_probe.py`

## Optimization

Bind the active derived-model id cache once in the `derived_model_id`-only branch and reuse it for the trimmed-id fallback lookup. This preserves behavior while avoiding a redundant method call and attribute lookup on the fallback path. Extend the existing probe output with `resolve_trimmed_target_elapsed_ms_mean` so this fallback path is measured directly by local and CI probe runs.

## Verification plan

Run locally on Linux before PR:

1. Focused job-registry tests and probe-registration smoke tests from the registered probe.
2. Changed-scope coverage using the registered coverage command plus `scripts/changed_scope_coverage.py` for the touched paths.
3. Registered probe command, comparing `origin/main` baseline to the branch head through `scripts/pr_scoped_performance_run.py` for `job-registry-derived-model-single-pass`.

## Acceptance criteria

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched Python lines.
- Registered probe shows directionally acceptable runtime with no missing metrics.
- PR-scoped performance CI selects and completes `job-registry-derived-model-single-pass` before merge.
