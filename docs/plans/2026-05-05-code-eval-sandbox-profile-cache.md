# Code Eval Sandbox Profile Static Fragment Cache

## Goal

Reduce repeated static sandbox-profile construction in `worker.engine.code_eval_runner` while preserving the per-run temporary root permissions and existing code-evaluation behavior.

## Linux-only constraint

This slice is implemented and verified on Linux. The real sandbox executor is macOS-specific, so local verification targets the pure Python profile builder, focused unit tests, changed-scope coverage, and the PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_stdio_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Update the existing `code-eval-stdio-tail-single-stat` PR-scoped probe so it also measures sandbox-profile generation:

- `sandbox_profile_elapsed_ms_mean`: mean elapsed time for repeated `_sandbox_profile(...)` construction.
- `sandbox_profile_static_builds_mean`: structural count of static profile fragment rebuilds per sample.

The optimized path should rebuild static runtime/executable clauses once per process-environment cache key while still appending the current `temp_root` read/write allowances for every evaluation.

## Success metrics

- Focused pytest passes for the code-eval tests and probe-registry smoke tests.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local probe reports concrete sandbox-profile metrics and shows `sandbox_profile_static_builds_mean=1.0`.
- `git diff --check` passes.
