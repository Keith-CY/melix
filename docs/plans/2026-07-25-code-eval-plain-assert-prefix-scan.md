# Code Evaluation Plain Assert Prefix Scan

## Scope

This Python performance slice is limited to `worker.engine.code_eval_runner._count_plain_assert_statement_lines()` in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

It does not change code-evaluation behavior, sandbox execution, payload parsing, protobuf artifacts, or external APIs.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

That probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Optimization Hypothesis

The registered probe repeatedly counts large payloads where every line starts with `assert `. A prefix-specialized scan can count that common unindented assert-only shape before falling back to the existing general parser-preserving line scanner for blank lines, indentation, tab boundaries, mixed statements, inline asserts, comments, and multiline assertions.

Expected effect:

- reduce `code-eval-count-tests-line-scan` `plain_assert_elapsed_ms_mean` for assert-heavy one-line payloads;
- keep `assert_elapsed_ms_mean`, fallback `elapsed_ms_mean`, and `peak_bytes_mean` stable;
- preserve behavior for nested asserts, direct top-level asserts, syntax-error fallback, no-assert fallback, and nonblank line counting.

## Validation Plan

1. Run the registered focused pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at least 95% coverage for touched scope.
3. Run `scripts/code_eval_count_tests_probe.py` before and after the change and compare `plain_assert_elapsed_ms_mean`, `assert_elapsed_ms_mean`, `elapsed_ms_mean`, and `peak_bytes_mean`.
4. Use the GitHub PR-scoped performance workflow as the merge gate before squash merging.
