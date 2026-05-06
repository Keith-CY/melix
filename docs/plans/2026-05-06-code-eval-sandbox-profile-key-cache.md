# Code Eval Sandbox Profile Key Cache

## Goal

Reduce repeated Python-environment introspection while building code-evaluation sandbox profiles. The dynamic temporary-root clauses still differ per evaluation run, but the static profile cache key is process-environment derived and should not rebuild `sysconfig.get_paths()` for every `_sandbox_profile(...)` call.

## Touched Files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_stdio_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux Constraint

This is a Python-only slice under `services/mlx-worker-python`, so local Linux verification uses focused pytest, changed-scope coverage, and an explicit PR-scoped performance probe run. It does not require macOS/Swift local validation.

## Probe Definition

Reuse the existing registered PR-scoped probe:

- `code-eval-stdio-tail-single-stat`

The probe already measures sandbox profile generation. This slice extends the probe script with a structural `sandbox_profile_sysconfig_get_paths_calls_mean` metric so the optimization has a deterministic signal in addition to elapsed wall time.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage for touched executable Python/test/script lines is at least 95%.
- Local probe shows reduced sandbox profile elapsed time and reduced `sysconfig.get_paths()` calls versus `origin/main`.
- `git diff --check` passes.
