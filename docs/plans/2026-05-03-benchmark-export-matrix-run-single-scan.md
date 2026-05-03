# Benchmark Export Matrix-Run Single Scan

## Context

This slice is Python-only and Linux-verifiable from the worker workspace. The current `benchmark_export.py` implementation already uses a single `os.scandir()` pass for serving benchmark run discovery, but `_collect_benchmark_matrix_run(...)` still probes `bench-matrix-job.json`, `bench-matrix-summary.jsonl`, and `bench-matrix-requests.jsonl` with three separate `Path.is_file()` calls per run directory.

The repository already registers the scoped CI probe `benchmark-export-run-scan-single-pass`, so this slice should stay inside that measurable path instead of introducing a new probe family.

## Chosen Slice

- update `services/mlx-worker-python/worker/productization/benchmark_export.py`
- update `services/mlx-worker-python/tests/test_benchmark_export.py`
- update `infra/perf/pr_scoped_probes.json` only if the existing focused test or coverage command needs tightening for the touched matrix-run behavior

Goal: make `_collect_benchmark_matrix_run(...)` discover its three artifact files with one directory scan while preserving output ordering, fallback behavior, and JSON/JSONL loading semantics.

## Linux Constraint

This work is limited to the Python worker/export path and can be verified locally on Linux. No macOS or Swift validation is required for correctness, but the existing PR-scoped performance CI must still validate the registered scoped probe after push.

## Probe Definition

Registered scoped CI probe: `benchmark-export-run-scan-single-pass` in `infra/perf/pr_scoped_probes.json`.

Local measurement path before commit:

- run the focused benchmark export pytest slice
- run changed-scope coverage for the touched executable lines
- run the existing benchmark export scoped probe and record concrete metrics such as:
  - `elapsed_ms_mean`
  - `per_run_ms_mean`
  - `csv_elapsed_ms_mean`

Success criteria:

1. matrix-run artifact collection remains behavior-identical
2. changed executable line coverage for the touched scope is at least 95%
3. the local probe does not regress versus the current baseline and ideally improves `elapsed_ms_mean` and `per_run_ms_mean`

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_summary_csv_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_summary_csv_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_benchmark_export.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_export_run_scan as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```