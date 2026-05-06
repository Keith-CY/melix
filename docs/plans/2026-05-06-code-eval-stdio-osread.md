# Code evaluation stdio tail OS-read slice

## Scope

This slice is limited to the Python worker code-evaluation stdio tail reader:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`

The behavior remains unchanged: missing, raced-away, unreadable, directory, and oversized stdio paths still return the same `(tail, size)` contract used by code evaluation failure reporting.

## Registered probe

The affected path is already covered by the PR-scoped performance probe `code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- a focused `test_command` for code-evaluation stdio behavior and probe selection,
- a `coverage_command` that measures changed-scope coverage for the code-eval runner, its tests, and the probe script,
- a `probe_command` that exercises repeated oversized stdout/stderr tail reads and reports `elapsed_ms_mean` plus `stdio_stat_calls_mean`.

## Optimization

Replace the `Path.stat()` + `Path.open()` + file-object `seek/read` sequence in `_read_limited_stdio()` with one descriptor-based path:

1. `os.open()` the stdio file once,
2. `os.fstat()` the opened descriptor so size and handle are consistent,
3. `os.lseek()` only when the file exceeds the retained tail byte limit,
4. `os.read()` the exact byte count and close the descriptor in `finally`.

This keeps the same single size lookup per file while avoiding Python file-object allocation and reducing the race window between stat and open.

## Verification plan

Run the registered probe's focused local Linux checks:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_returns_timeout_result services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_uses_stderr_when_payload_is_missing services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_skips_parent_test_counting_after_successful_payload services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_text_handles_missing_and_oversized_files services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_handles_open_race services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_ignores_close_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_output_limit_reuses_limited_stdio_sizes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_stdio_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_returns_timeout_result services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_uses_stderr_when_payload_is_missing services/mlx-worker-python/tests/test_code_eval_runner.py::test_run_python_code_evaluation_skips_parent_test_counting_after_successful_payload services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_text_handles_missing_and_oversized_files services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_handles_open_race services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_ignores_close_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_output_limit_reuses_limited_stdio_sizes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_stdio_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_stdio_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_stdio_probe.py
```

## Success criteria

- Focused behavior tests pass on Linux.
- Changed-scope coverage for touched Python code remains at or above 95%.
- Local registered probe reports a lower `elapsed_ms_mean` than the origin/main baseline while preserving `stdio_stat_calls_mean == 6000.0` and the same output-limit/tail guard values.
- PR-scoped performance CI selects and completes `code-eval-stdio-tail-single-stat`.
