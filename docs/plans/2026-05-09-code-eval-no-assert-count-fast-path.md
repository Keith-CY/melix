# Code Evaluation No-Assert Test Count Fast Path

## Scope

This performance slice is limited to the Python code-evaluation test counter in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The optimization keeps the existing assertion-count semantics while avoiding AST parsing for fallback test payloads that do not contain the `assert` keyword at all. Those payloads can only resolve through the nonblank-line fallback, so the counter can stream the existing regex line scan immediately.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. This slice updates the focused command set with a regression test that proves the no-assert fast path skips `ast.parse`.

## Plan

1. Add a regression test for no-assert test payloads that fails if AST parsing is invoked.
2. Short-circuit `_count_tests()` to `_count_nonblank_test_lines()` when the payload contains no `assert` keyword.
3. Keep syntax-error and assert-containing payload behavior unchanged.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before opening the PR.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_reuses_cached_counts_for_repeated_payloads services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_test_lines_matches_splitlines_semantics services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_fallback_avoids_splitlines_materialization services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_avoids_splitlines_materialization services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fast_path_skips_ast_parse services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_count_tests_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_reuses_cached_counts_for_repeated_payloads services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_test_lines_matches_splitlines_semantics services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_fallback_avoids_splitlines_materialization services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_avoids_splitlines_materialization services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fast_path_skips_ast_parse services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_count_tests_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_count_tests_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_count_tests_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
