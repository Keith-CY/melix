# Code Eval Test Counting Splitlines Fast Path

This Python-only performance slice is limited to the fallback nonblank-line counter used by `worker.engine.code_eval_runner._count_tests` when test code has no `assert` token or cannot be parsed as Python AST.

Registered PR-scoped probe: `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`.

## Optimization

Add a bounded fast path that replaces the Python character-by-character nonblank line scan with Python's built-in `str.splitlines()` plus `str.strip()` filtering for typical fallback payloads. Keep the streaming character scan for very large inputs so the existing nonblank streaming probe does not regress memory usage. The fallback counter already defines behavior in terms of splitline semantics in tests, and the registered probe exercises both syntax-error and no-assert fallback paths with synthetic test payloads.

## Verification Plan

Run the registered focused test command, coverage command, and probe command locally on Linux:

```bash
Use the exact `test_command` and `coverage_command` registered for `code-eval-count-tests-line-scan`.
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_count_tests_probe.py
```

## Acceptance

Accept this slice only if focused behavior tests pass, changed-scope coverage stays at or above the repository threshold, and the registered probe shows lower `elapsed_ms_mean` without a blocking regression.
