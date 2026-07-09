# Code eval assert-line count fast path

## Scope

This Python-only performance slice is limited to test-count estimation in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

Code-evaluation fixtures frequently contain large payloads made only of simple
one-line `assert` statements. The previous path parsed those payloads into an
AST before counting the assertion nodes. This slice adds a narrow pre-parse path
that counts simple assert-only line payloads directly, while preserving the AST
path for mixed statements, inline asserts, comments, strings, and multiline
assertions.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for the touched worker path. The registered probe
remains stable for CI gating; this slice records an additional local same-script
microbenchmark for the assert-only `_count_tests()` path because the existing
probe's `assert_elapsed_ms_mean` metric targets the lower-level AST walker.

## Plan

1. Add regression coverage proving assert-only payloads skip AST parsing, while
   mixed payloads still defer to the parser and preserve assertion counts.
2. Add a direct assert-line counter before `ast.parse()` in `_count_tests()`.
3. Keep the registered probe script stable for CI gating and run an additional
   same-script local microbenchmark for the optimized assert-only `_count_tests()`
   path.
4. Run the focused registered tests, changed-scope coverage, and the registered
   probe locally on Linux.
5. Use GitHub Actions and the PR-scoped performance report as the merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_syntax_error_fallback_uses_nonblank_line_counter services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_test_lines_matches_splitlines_semantics services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_without_filtered_list services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_short_inputs_without_splitlines services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_when_no_asserts_are_present services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_uses_nonblank_line_counter services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_plain_assert_lines_skip_ast_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_plain_assert_fast_path_defers_mixed_statements services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_count_tests_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_syntax_error_fallback_uses_nonblank_line_counter services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_test_lines_matches_splitlines_semantics services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_without_filtered_list services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_short_inputs_without_splitlines services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_when_no_asserts_are_present services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_uses_nonblank_line_counter services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_plain_assert_lines_skip_ast_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_plain_assert_fast_path_defers_mixed_statements services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_count_tests_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_count_tests_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_count_tests_probe.py
```
