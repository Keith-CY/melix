# Code eval stdio read-limit fast path

## Scope

This Python-only performance slice is limited to the code-evaluation stdio tail
reader in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The optimization preserves existing subprocess stdout/stderr tail semantics while
removing per-call `int(...)`/`max(...)` helper overhead from `_read_limited_stdio`
for the registered positive integer `stdout_limit_bytes` path. Negative or zero
limits still clamp to zero bytes.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`.

The registry entry already provides focused `test_command`, `coverage_command`,
and `probe_command` entries for the touched worker path. This slice keeps the
probe registry stable and uses the registered local/CI probe as the performance
gate.

## Plan

1. Keep the existing stdio race/error tests as the behavior parity guard.
2. Replace `max(int(byte_limit), 0)` with a direct positive-integer branch,
   collapse the read-size selection to a single expression, and return early for
   zero-byte reads.
3. Run the focused code-eval pytest targets, changed-scope coverage, and the
   registered `code_eval_stdio_probe.py` on Linux before opening the PR.
4. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_text_handles_missing_and_oversized_files services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_handles_open_race services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_ignores_close_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_output_limit_reuses_limited_stdio_sizes services/mlx-worker-python/tests/test_code_eval_runner.py::test_timeout_and_output_limit_failure_details_include_stdio_when_present services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_stdio_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_text_handles_missing_and_oversized_files services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_handles_open_race services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_limited_stdio_ignores_close_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_output_limit_reuses_limited_stdio_sizes services/mlx-worker-python/tests/test_code_eval_runner.py::test_timeout_and_output_limit_failure_details_include_stdio_when_present services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_stdio_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_stdio_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_stdio_probe.py
```
