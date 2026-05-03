# Benchmark Export Shared Run Scan Optimization

## Goal

Reduce redundant filesystem scanning in `services/mlx-worker-python/worker/productization/benchmark_export.py` when `build_export_bundle()` assembles mixed benchmark and evaluation artifacts from the same artifact root.

## Linux Constraint

This slice is Python-only and will be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit local performance probe.

## Touched Files

- `docs/plans/2026-05-03-benchmark-export-shared-run-scan.md`
- `services/mlx-worker-python/worker/productization/benchmark_export.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_benchmark_export.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Design

- Add a small internal scanned-run helper so benchmark and evaluation collectors can reuse one directory listing.
- Keep the public `collect_benchmark_artifacts()` and `collect_evaluation_artifacts()` behavior unchanged.
- Optimize only `build_export_bundle()` for the shared-root case by reusing one scan of the root and one scan per shared `runs/*` directory while preserving output payload shape and ordering.
- Update the existing `benchmark-export-run-scan-single-pass` PR-scoped performance probe so it measures the mixed benchmark+evaluation bundle path instead of only the benchmark-only path.

## Probe Definition

- Probe ID: `benchmark-export-run-scan-single-pass`
- Measurement path: `_probe_benchmark_export_run_scan(...)` in `pr_scoped_performance.py`
- Synthetic workload: mixed benchmark + evaluation artifacts under one shared root with a shared `runs/` directory.
- Primary success signal: lower `elapsed_ms_mean` for `build_export_bundle(...)` while preserving the expected benchmark/evaluation counts.
- Secondary signal: lower `per_run_ms_mean`.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_summary_csv_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_export_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_job_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_result_count \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_export_run_scan_rejects_unexpected_summary_csv_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python -c \
  "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_export_run_scan as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```

## Success Criteria

- Focused tests pass.
- Changed-scope coverage for touched executable lines is at least 95%.
- The updated mixed bundle probe reports preserved artifact counts and lower bundle scan time versus `origin/main`.
- No unrelated files are changed.
