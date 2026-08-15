# Code evaluation assert prescan regex fast path

This Python performance slice is limited to `worker.engine.code_eval_runner._may_contain_assert_statement`.

## Registered performance probe

The affected code path is already covered by the registered PR-scoped probe `code-eval-assert-mention-prescan` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_assert_prescan_regex.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_assert_prescan_probe.py`

## Slice

Replace the Python-level repeated `str.find()` assert-token scan with a compiled regular expression that preserves the same statement-boundary rules: start-of-input or newline/semicolon/colon after optional horizontal spacing, followed by `assert` and a non-identifier follower.

## Verification plan

1. Run the focused code-eval assert prescan tests.
2. Run the registered `code-eval-assert-mention-prescan` coverage command.
3. Run the registered local probe on Linux.
4. Treat `elapsed_ms_mean` as the primary latency gate. `peak_bytes_mean` remains lower-is-better, with a 2 KiB absolute tolerance so the compiled-search match allocation does not make sub-kilobyte tracemalloc noise fail an otherwise lower-latency slice.
5. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.
