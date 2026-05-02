# 2026-05-02 Benchmark Export CSV Writerows

## Context

This slice is Python-only and Linux-verifiable. `benchmark_export.py` is already covered by the registered PR-scoped probe `benchmark-export-run-scan-single-pass`, including focused test, coverage, and probe commands.

## Chosen Slice

Optimize `_rows_to_csv(...)` in `services/mlx-worker-python/worker/productization/benchmark_export.py` by replacing per-row `csv.DictWriter.writerow(...)` dictionaries with a streaming `csv.writer.writerows(...)` generator.

## Optimization Hypothesis

The current CSV helper allocates one filtered dictionary per output row before handing data to `DictWriter`. The output schema is fixed by the caller-provided `fieldnames`, so a streaming list of normalized values can preserve column order and CSV quoting while avoiding the intermediate dictionary allocation and DictWriter extras filtering per row.

## Probe Coverage

Registered PR-scoped probe: `benchmark-export-run-scan-single-pass` in `infra/perf/pr_scoped_probes.json`.

This slice extends the probe to also call `build_benchmark_summary_csv(...)` and report:

- `csv_elapsed_ms_mean` — target metric for this CSV writer slice
- `csv_bytes` — output-size correctness guard rail
- existing benchmark-export scan metrics (`elapsed_ms_mean`, `per_run_ms_mean`, `result_file_count`, `run_directory_count`)

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 <probe runner for _probe_benchmark_export_run_scan>

git diff --check
```

## Success Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Local probe reports a lower `csv_elapsed_ms_mean` on head than the pre-change baseline.
- The registered PR-scoped performance probe completes successfully in CI.
