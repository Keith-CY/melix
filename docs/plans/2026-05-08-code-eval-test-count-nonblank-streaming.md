# Code Eval Test Count Nonblank Streaming Optimization

## Goal

Reduce temporary allocation pressure in the code-evaluation test-count fallback path by replacing list-materialized nonblank-line counting with a streaming generator count.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be verified locally on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_test_count_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Register `code-eval-test-count-nonblank-streaming` in the PR-scoped performance registry. The probe builds a large synthetic test-code payload and measures `_count_nonblank_lines(...)` directly, reporting:

- `elapsed_ms_mean` (informational; lower is better but allocation is the main win)
- `peak_bytes_mean` (lower is better)
- `line_count`
- `nonblank_line_count_mean`

## Success metrics

- Focused tests for syntax-error and no-assert fallback paths pass.
- Changed-scope coverage for touched executable Python scope is at least 95%.
- The local base-vs-head scoped probe shows materially lower `peak_bytes_mean` with identical nonblank line counts.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_for_syntax_error_input \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_syntax_error_fallback_uses_nonblank_line_counter \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_nonblank_lines_streams_without_filtered_list \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_falls_back_when_no_asserts_are_present \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_count_tests_no_assert_fallback_uses_nonblank_line_counter \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_test_count_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same nodes>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/code_eval_runner.py \
  services/mlx-worker-python/tests/test_code_eval_runner.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/code_eval_test_count_probe.py

python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id code-eval-test-count-nonblank-streaming \
  --base-repo /tmp/melix-origin-main-code-eval-count \
  --head-repo "$PWD" \
  --output /tmp/code-eval-test-count-probe.json

git diff --check
```
