# Code Evaluation Assert Node Len Binding

## Scope

This Python performance slice is limited to `worker.engine.code_eval_runner._count_assert_nodes()` in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

It does not change code-evaluation behavior, sandbox execution, payload parsing, protobuf artifacts, or external APIs.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

That probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Optimization Hypothesis

The registered probe exercises the top-level assert-only AST fast path repeatedly through `_count_assert_nodes(...)`. Binding `len` as a function default lets the fast path return the already-validated module body length without a repeated global builtin lookup while preserving the existing exact-`ast.Assert` validation before the return.

Expected effect:

- reduce or keep neutral `code-eval-count-tests-line-scan` `assert_elapsed_ms_mean` for assert-heavy top-level payloads;
- keep fallback `elapsed_ms_mean` and `peak_bytes_mean` stable;
- preserve behavior for nested asserts, direct top-level asserts, AST subclasses, syntax-error fallback, no-assert fallback, and nonblank line counting.

## 2026-08-18 follow-up: module-local assert count cache

This follow-up keeps the same registered `code-eval-count-tests-line-scan` probe and remains limited to `_count_assert_nodes(...)`. Code-evaluation runs parse a test module once and may count assert nodes repeatedly while building focused metrics. The helper now stores the computed assert count on the parsed AST module after the first exact-type traversal, so repeated calls on the same module avoid re-walking the top-level assert list or nested statement containers.

Expected effect:

- reduce `code-eval-count-tests-line-scan` `assert_elapsed_ms_mean` for repeated assert-heavy AST counting;
- keep plain assert counting, syntax-error fallback, no-assert fallback, and nonblank line counting behavior unchanged;
- keep `peak_bytes_mean` neutral or lower apart from the one module-local integer attribute.

## Validation Plan

1. Run the registered focused pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at least 95% coverage for touched scope.
3. Run `scripts/code_eval_count_tests_probe.py` before and after the change and compare `assert_elapsed_ms_mean`, `plain_assert_elapsed_ms_mean`, `elapsed_ms_mean`, and `peak_bytes_mean`.
4. Use the GitHub PR-scoped performance workflow as the merge gate before squash merging.
