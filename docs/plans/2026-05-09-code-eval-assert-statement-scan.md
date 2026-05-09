# Code Evaluation Assert Statement Scan Slice

## Scope

This Python-only performance slice is limited to valid assertion-count payloads in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The existing fallback fast paths for syntax-error and no-`assert` payloads remain
unchanged. For syntactically valid test payloads, `_count_tests()` now walks only
statement/container nodes instead of traversing expression subtrees with
`ast.walk()`. Python `assert` is a statement, so expression nodes cannot add new
assert-count evidence.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`. This
slice extends `scripts/code_eval_count_tests_probe.py` with a valid-assert sample
that reports `valid_assert_elapsed_ms_mean` while preserving the existing
fallback metrics.

## Behavior Guard

Focused regression coverage verifies that assert statements nested in `if`,
`try`/`except`, and `match` bodies are counted, while text containing `assert`
inside string literals is ignored.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux. The PR-scoped performance workflow remains the merge gate for
the registered probe report.

## Success Criteria

- Focused code-evaluation tests pass.
- Changed-scope coverage remains at or above 95%.
- Local probe preserves fallback counts and shows lower valid-assert count time.
- GitHub Actions and the PR-scoped performance workflow are green.
