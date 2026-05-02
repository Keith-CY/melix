# PR-scoped Performance Report Results Scandir Slice

## Goal

Reduce filesystem overhead when the PR-scoped performance report command loads many probe result JSON files from its results directory.

## Scope

- `scripts/pr_scoped_performance_report.py`
- `scripts/pr_scoped_performance_report_results_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This slice is Python-only and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped probe.

## Optimization Hypothesis

`_load_results()` previously used `Path.glob("*.json")`, which allocates `Path` entries through pathlib globbing before reading result files. Replacing that enumeration with `os.scandir()` keeps the same sorted JSON loading behavior while using lower-overhead directory iteration for large PR-scoped probe result sets.

## Registered Probe

- Probe ID: `pr-scoped-performance-report-results-scandir`
- Workload: create 2,000 synthetic probe result JSON files plus an ignored non-JSON file, then load the result directory five times.
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `elapsed_ms_min` lower is better
  - `file_count`, `result_count`, and `sample_count` informational

## Success Metrics

- Focused tests prove the report loader no longer relies on `Path.glob()` and still returns sorted JSON payloads.
- Changed-scope coverage for the touched report script, probe script, and tests remains at or above 95%.
- Local registered probe improves versus the pre-change baseline.
- PR-scoped performance CI selects and completes the registered probe for this path.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_performance_report_results_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_results_loader_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_performance_report_results_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_performance_report_results_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_results_loader_uses_scandir_without_path_glob services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_performance_report_results_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/pr_scoped_performance_report.py scripts/pr_scoped_performance_report_results_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_report_results_probe.py
git diff --check
```
