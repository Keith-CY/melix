# Code Eval Count Tests Nonempty Line Streaming

## Goal

Reduce peak memory in the Python code-evaluation test-count fallback path by avoiding list materialization when counting nonempty test lines.

## Linux-only constraint

This slice touches only Python worker code and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_stdio_probe.py`

## Performance probe definition

Extend the code-evaluation stdio probe script to measure `_count_tests(...)` on large fallback inputs:

- syntax-error input, which forces the parser fallback
- parseable input with no `assert`, which forces the no-assert fallback

Metrics:

- `count_tests_elapsed_ms_mean`
- `count_tests_peak_bytes_mean`
- `count_tests_line_count`
- `count_tests_result_mean`

Success means behavior is unchanged while peak traced allocation drops materially against the old list-building fallback.

## Verification commands

- Focused pytest for the code-evaluation fallback and probe script smoke tests.
- Changed-scope coverage via `scripts/changed_scope_coverage.py`, requiring >=95% for changed executable scope.
- `python scripts/code_eval_stdio_probe.py` for local concrete probe metrics.
- `git diff --check`.
