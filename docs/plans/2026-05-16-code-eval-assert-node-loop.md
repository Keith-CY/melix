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

`_count_assert_nodes()` already avoids `ast.walk()` by using a single explicit
stack over statement container nodes. This follow-up counts top-level assert
nodes while seeding the stack, avoiding stack push/pop work for common flat test
modules, then keeps the existing stack traversal for nested statement
containers. It also removes the per-container generator expression passed to
`stack.extend(...)` and appends matching child statement containers directly.
The traversal order is not observable because the helper only counts
`ast.Assert` nodes, and behavior stays unchanged for nested asserts and modules
without asserts.

2026-06-14 follow-up: the all-top-level-assert fast path now uses an explicit
loop/`else` instead of `all(...)` with a generator expression. The probe's
`assert_elapsed_ms_mean` path repeatedly counts a flat assert module, so this
slice avoids generator overhead while preserving the nested traversal fallback
for mixed or nested statement containers.

## Verification Plan

- Run focused code-evaluation count tests, including the new no-assert helper
  regression check.
- Run changed-scope coverage through the registered probe coverage command.
- Run the registered `code-eval-count-tests-line-scan` probe locally on Linux
  before and after the change and compare `peak_bytes_mean` and elapsed metrics.

## Linux Boundary

This slice is Python-only and locally verifiable on Linux. Swift/macOS runtime
effects are not involved.
