# Code evaluation assert boundary fast path

## Scope

This Python-only performance slice is limited to the fallback code-evaluation test counter in `worker.engine.code_eval_runner`.

The change preserves plain assert-line detection while avoiding a per-line `str.isalnum()` call for the common `assert ` and `assert\t` boundaries in synthetic and benchmark-style test payloads.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

That probe declares focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_count_tests_probe.py`

## Implementation plan

1. Add regression coverage for space and tab boundaries after the `assert` keyword.
2. Short-circuit those common boundaries before the slower identifier-character check.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the merge validation source.

## Linux verification boundary

This slice changes Python code and is locally verifiable on Linux. No Swift runtime behavior is changed.