# Code evaluation plain assert character scan

## Scope

This Python-only performance slice is limited to `_count_plain_assert_statement_lines()` in `worker.engine.code_eval_runner`.

The helper is the fast path for code-evaluation test payloads where every nonblank line is a plain top-level `assert` statement. It currently uses `str.startswith("assert", cursor)` for each nonblank line and then separately checks the following boundary character.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

The probe declares focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

No probe registry change is required for this narrow helper optimization.

## Implementation plan

1. Preserve the existing plain-assert boundary semantics, including short non-assert prefixes and identifier-prefixed names.
2. Replace the per-line `startswith()` helper call with direct fixed-character checks for the six-character `assert` token before reading the boundary character.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the merge gate.

## Metrics expectation

The registered `code-eval-count-tests-line-scan` probe should show lower `elapsed_ms_mean` for the syntax-error/no-assert fallback workload, while `assert_elapsed_ms_mean` and behavior remain stable. Peak allocation should not increase.

## Linux verification boundary

This slice changes Python code only and is locally verifiable on Linux. No Swift runtime behavior is changed.
