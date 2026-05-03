# Job Registry Derived-Model Lookup Optimization

## Goal

Avoid building a full job-registry snapshot when the caller only needs active derived-model manifests or one derived-model target lookup.

## Linux-Only Constraint

This slice targets Python worker code only and will be verified locally on Linux.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/job_registry.py`
- `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/job_registry_derived_model_probe.py`

## Hypothesis

`active_derived_model_manifests()` and `resolve_derived_model_target()` currently materialize broad snapshot-style job payloads even though they only need a narrow subset of activation/removal data. A dedicated single-pass helper over in-memory jobs should reduce redundant work and temporary object creation.

## Performance Probe

Probe id: `job-registry-derived-model-single-pass`

Measurement path:
- construct a large synthetic `ModelOpsJobRegistry` with many completed `train_lora`, `activate_adapter`, and `remove_derived_model` jobs
- measure `active_derived_model_manifests()` and `resolve_derived_model_target()` over multiple samples
- record mean elapsed milliseconds and manifest count / lookup hit to prove semantics stay intact

## Success Metrics

- Preserve current lookup/removal behavior
- Focused tests pass
- Changed-scope automated coverage is at least 95%
- Local probe shows lower `elapsed_ms_mean` for the active-manifest and target-lookup path versus `origin/main`

## Verification Commands

- Focused RED/GREEN pytest for the new regression tests
- Focused pytest for touched scope
- `coverage run -m pytest ...` + changed-scope coverage report
- Local probe script on `origin/main` and the branch implementation
- `git diff --check`
