# Code Evaluation Nonblank Counter Streaming

This Python-only performance slice is limited to fallback test counting in
`worker.engine.code_eval_runner._count_nonblank_test_lines()`.

## Scope

The fallback path is used when code-evaluation test snippets cannot be parsed as
Python or contain no executable `assert` nodes. The current short-input branch
uses `str.splitlines()`, which materializes a full line list during fallback
counting. This slice keeps the same nonblank-line semantics while using the
existing streaming counter for all input sizes, reducing transient allocations on
small and medium fallback snippets as well as large snippets.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`, which
includes focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

The local Linux validation for this slice uses that registered probe. GitHub
Actions PR-scoped performance remains the merge gate.

## Implementation plan

1. Add a regression test proving short fallback snippets avoid `splitlines()`.
2. Remove the short-input `splitlines()` branch from `_count_nonblank_test_lines()`.
3. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux before opening the PR.
4. Merge only after GitHub Actions and the registered PR-scoped performance
   report are green.

## Success criteria

- Fallback line-count behavior remains equivalent to `splitlines()` semantics for
  existing ASCII and Unicode boundaries.
- Changed-scope coverage for touched files remains at least 95%.
- Registered probe shows reduced allocation pressure without a blocking elapsed
  regression.
