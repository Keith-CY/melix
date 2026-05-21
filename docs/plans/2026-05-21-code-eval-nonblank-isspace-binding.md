# Code Eval Nonblank Line Counter Local Binding

## Scope

This Python-only performance slice is limited to `_count_nonblank_test_lines(...)`
in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe
`code-eval-test-count-nonblank-streaming` in `infra/perf/pr_scoped_probes.json`.
The registered entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_test_count_probe.py`

## Optimization

The counter already streams over the source text to avoid allocating a filtered
line list. This slice keeps that behavior and binds `str.isspace` once before
the hot character loop, avoiding repeated bound-method lookup for every
non-newline character while preserving whitespace semantics.

## Verification Plan

1. Run the focused registered test command locally on Linux.
2. Run the changed-scope registered coverage command locally on Linux and require
   at least 95% coverage for touched code.
3. Run the registered probe locally before and after the slice, comparing
   `elapsed_ms_mean`, `peak_bytes_mean`, and `nonblank_line_count_mean`.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered
   probe report.

## Success Criteria

- Nonblank line counts remain identical for the focused code-eval tests.
- Local probe keeps `peak_bytes_mean` flat and improves `elapsed_ms_mean` versus
  the pre-change Linux baseline.
- PR-scoped performance CI completes successfully for
  `code-eval-test-count-nonblank-streaming`.
