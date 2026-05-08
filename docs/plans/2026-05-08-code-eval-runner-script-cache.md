# Code Eval Runner Script Cache Optimization

## Goal

Avoid rebuilding and dedenting the static Python code-evaluation runner script on every `run_python_code_evaluation(...)` request.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_runner_script_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This is a Python-only change and is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Performance probe

Register `code-eval-runner-script-cache` in `infra/perf/pr_scoped_probes.json`.

The probe repeatedly calls `_runner_script()` and reports:

- `elapsed_ms_mean` lower is better
- `dedent_calls_mean` lower is better, expected `1.0` per sample on the optimized branch
- `peak_bytes_mean` lower is better
- `identity_reuse_mean` higher is better, expected `1.0` on the optimized branch

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local base-vs-head probe shows fewer repeated `textwrap.dedent(...)` calls and lower elapsed time/allocations.
- `git diff --check` passes.
