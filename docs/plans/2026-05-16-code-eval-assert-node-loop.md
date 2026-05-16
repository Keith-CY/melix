# Code Evaluation Assert Node Stack Slice

## Scope

This Python-only performance slice is limited to valid assert-node counting in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. Its checked-in probe exercises repeated
`_count_assert_nodes()` calls under `tracemalloc`, so the registered
`peak_bytes_mean` metric captures allocation pressure for this helper.

## Optimization

`_count_assert_nodes()` previously used `ast.walk()`, which creates and manages
an internal queue while yielding every AST node. This slice replaces it with a
single explicit stack over `ast.iter_child_nodes()`. The traversal order is not
observable because the helper only counts `ast.Assert` nodes, and behavior stays
unchanged for nested asserts and modules without asserts.

## Verification Plan

- Run focused code-evaluation count tests, including the new no-assert helper
  regression check.
- Run changed-scope coverage through the registered probe coverage command.
- Run the registered `code-eval-count-tests-line-scan` probe locally on Linux
  before and after the change and compare `peak_bytes_mean` and elapsed metrics.

## Linux Boundary

This slice is Python-only and locally verifiable on Linux. Swift/macOS runtime
effects are not involved.
