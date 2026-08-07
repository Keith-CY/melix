# Code Evaluation Assert Prescan Local Bindings

## Scope

This Python performance slice is limited to `worker.engine.code_eval_runner._may_contain_assert_statement()` in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

It does not change code-evaluation behavior, sandbox execution, payload parsing, protobuf artifacts, or external APIs.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

That probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Optimization Hypothesis

The assertion pre-scan runs before AST parsing and is exercised repeatedly by the registered fallback test-count probe. Binding `str.find`, `str.isalnum`, and the small boundary sets as function defaults should avoid repeated global or bound-method lookups in the scan loop while preserving the existing token-boundary semantics.

Expected effect:

- reduce or keep neutral `code-eval-count-tests-line-scan` `elapsed_ms_mean` for syntax-error/no-assert fallback workloads;
- keep `assert_elapsed_ms_mean` stable for assert-heavy payloads;
- preserve behavior for comments, strings, identifier prefixes, inline assert statements, spacing, and boundary detection.

## Validation Plan

1. Run the registered focused pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at least 95% coverage for touched scope.
3. Run `scripts/code_eval_count_tests_probe.py` before and after the change and compare `elapsed_ms_mean`, `assert_elapsed_ms_mean`, and `peak_bytes_mean`.
4. Use the GitHub PR-scoped performance workflow as the merge gate before squash merging.
