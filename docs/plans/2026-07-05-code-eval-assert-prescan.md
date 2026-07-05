# Code Eval Assert Pre-scan Performance Slice

## Scope

This Python-only performance slice is limited to `worker.engine.code_eval_runner._count_tests()` and the fallback test-count probe.

The optimization avoids building a Python AST when executable-code evaluation test payloads only mention `assert` inside comments or string literals. The behavior remains unchanged: valid `assert` statements are still counted through the AST path, syntax-error payloads with real `assert` statements still fall back to the nonblank-line counter, and no-assert payloads continue to report nonblank test lines.

## Registered Probe

The affected path is covered by the existing registered PR-scoped probe `code-eval-count-tests-line-scan` and this slice adds the focused registered probe `code-eval-assert-mention-prescan` in `infra/perf/pr_scoped_probes.json` with dedicated `test_command`, `coverage_command`, and `probe_command` entries.

The new probe uses the same comment/string-literal `assert` mention workload on base and head so CI can validate the pre-scan behavior against the previous implementation without changing the existing count-tests probe workload.

## Verification Plan

Run locally on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_reuses_cached_counts_for_repeated_payloads \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_assert_nodes_counts_nested_asserts \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_assert_nodes_uses_exact_type_for_direct_asserts \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_assert_nodes_fast_paths_all_top_level_asserts \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_test_lines_matches_splitlines_semantics \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_fallback_counts_nonblank_lines \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_counts_nonblank_lines \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fast_path_skips_ast_parse \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_ignores_assert_tokens_in_comments_and_strings \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_preserves_inline_assert_statement_detection \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_without_filtered_list \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_short_inputs_without_splitlines \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_count_tests_probe_script_emits_metrics
```

Also run the registered changed-scope coverage command and probe command from `infra/perf/pr_scoped_probes.json`. GitHub Actions PR-scoped performance remains the merge gate.

## Metrics

Target metrics:

- `peak_bytes_mean`: lower is better for the assert-mention pre-scan workload because the slice avoids allocating an AST for common comment/string `assert` mentions.
- `elapsed_ms_mean`: tracked as lower-is-better in the registered probe to surface CPU trade-offs; local Linux measurements showed the memory win with a small elapsed-time regression, so CI should be inspected before merge rather than treating this as an unconditional latency improvement.
- `assert_elapsed_ms_mean`: should remain stable for true assert-node counting in the existing count-tests probe.

## Known Boundaries

This is a Linux-verifiable Python slice. It does not change sandbox execution behavior, candidate-code execution, Swift code, protobuf schemas, or generated artifacts.
