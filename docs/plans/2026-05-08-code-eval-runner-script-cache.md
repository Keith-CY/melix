# Code Eval Runner Script Cache Optimization

## Goal

Avoid rebuilding or dedenting the static Python code-evaluation runner script in the hot `_runner_script()` accessor used by each sandboxed evaluation.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_runner_script_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This is a Python-only change and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json PR-scoped performance probe.

## Performance probe

Registered probe: `code-eval-runner-script-cache` in `infra/perf/pr_scoped_probes.json`.

The probe repeatedly calls `_runner_script()` and reports:

- `elapsed_ms_mean` lower is better
- `dedent_calls_mean` lower is better; this slice expects `0.0` because the dedented static payload is precomputed outside the accessor
- `peak_bytes_mean` lower is better
- `identity_reuse_mean` higher is better, expected `1.0` on the optimized branch

## Implementation

- Precompute the dedented runner script once at module import as `_RUNNER_SCRIPT`.
- Keep `_runner_script()` as the existing cached accessor so callers retain the same API.
- Preserve generated runner content, including the final newline.
- Keep the focused test assertion that monkeypatched `textwrap.dedent` is not reached from `_runner_script()` calls.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local base-vs-head probe shows `dedent_calls_mean` dropping from `1.0` to `0.0` and lower `elapsed_ms_mean` for the registered probe.
- `git diff --check` passes.
