# Benchmark export scanned-entry membership cache

## Goal

Reduce repeated linear membership checks in benchmark/evaluation export directory scan results while preserving deterministic file ordering.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_export.py`
- `services/mlx-worker-python/tests/test_benchmark_export.py`

## Linux-only constraint

This is a Python worker/productization slice. It is fully verifiable on Linux with focused pytest, changed-scope coverage, `git diff --check`, and the existing registered PR-scoped performance probe.

## Optimization

`_scan_directory(...)` already pays for one sorted scan per run directory and stores sorted file/dir name tuples. Hot marker checks in `_ScannedDirectoryEntries.file_path(...)` and `.has_dir(...)` repeatedly used tuple membership, which is O(n) for large artifact directories. Cache `frozenset` views at construction time and keep sorted tuples for deterministic iteration and matching.

## Performance probe

Registered scoped CI probe: `benchmark-export-run-scan-single-pass`.

Local explicit probe: run `scripts/pr_scoped_performance_run.py --probe-id benchmark-export-run-scan-single-pass` against the branch and compare with a detached `origin/main` worktree when feasible.

Success metric: lower or equal `elapsed_ms_mean` for the benchmark export run-scan probe with unchanged artifact counts. The unit regression test also proves hot membership calls no longer query tuple membership.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_export.py::test_scanned_directory_entry_membership_uses_name_sets services/mlx-worker-python/tests/test_benchmark_export.py::test_collect_benchmark_run_uses_single_directory_scan_without_path_is_file_probes services/mlx-worker-python/tests/test_benchmark_export.py::test_collect_evaluation_run_uses_single_directory_scan_without_path_is_file_probes

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_export.py::test_scanned_directory_entry_membership_uses_name_sets services/mlx-worker-python/tests/test_benchmark_export.py::test_collect_benchmark_run_uses_single_directory_scan_without_path_is_file_probes services/mlx-worker-python/tests/test_benchmark_export.py::test_collect_evaluation_run_uses_single_directory_scan_without_path_is_file_probes
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_benchmark_export.py

git diff --check
```
