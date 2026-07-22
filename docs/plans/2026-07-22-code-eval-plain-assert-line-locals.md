# Code eval plain assert line locals

## Scope

This Python-only performance slice is limited to the code-evaluation plain assert
line counter in `worker.engine.code_eval_runner._count_plain_assert_statement_lines`.
The behavior remains unchanged: assert-only test payloads are counted without AST
construction, while mixed statements, assert-like identifiers, comments, and
inline assertions still fall back to the parser or existing nonblank-line paths.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`. This
slice extends the existing probe script with `plain_assert_elapsed_ms_mean` so
the CI report directly measures `_count_tests()` on a synthetic assert-only
payload, in addition to the existing fallback and AST-node metrics.

The registry entry keeps focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Implementation plan

1. Preserve the existing test-counting semantics with the focused code-eval tests.
2. Bind the plain-assert scanner's stable helpers as function defaults so the
   hot line loop avoids repeated global and attribute lookups.
3. Measure the registered probe locally on Linux against `origin/main` and the
   head branch.
4. Use the PR-scoped performance workflow as the merge gate.

## Expected metrics

Primary expected direction: lower `plain_assert_elapsed_ms_mean` in
`code-eval-count-tests-line-scan`. Existing `assert_elapsed_ms_mean`,
`elapsed_ms_mean`, and `peak_bytes_mean` should remain stable because this slice
only changes the plain assert-only scanner.
