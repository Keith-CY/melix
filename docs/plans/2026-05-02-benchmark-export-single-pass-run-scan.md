# 2026-05-02 Benchmark Export Single-Pass Run Scan

## Context

This cron run is limited to Linux-verifiable changes in `services/mlx-worker-python`.
The selected slice should reduce repeated filesystem work in benchmark export
collection while staying small, testable, and measurable on Linux.

## Chosen Slice

Optimize `services/mlx-worker-python/worker/productization/benchmark_export.py`
by collapsing repeated per-run filesystem probes in `_collect_benchmark_run()`
into a single deterministic directory scan that reuses discovered entries for
summary/job/context/batch/result loading.

## Why This Slice

- Pure Python and Linux-verifiable.
- Targets redundant hot-path filesystem work that still exists on `origin/main`.
- Preserves output shape, lexical ordering, and `bench-summary.json` preference.
- Has an existing focused test surface in `services/mlx-worker-python/tests/test_benchmark_export.py`.
- Can be validated with a synthetic local benchmark and a PR-scoped performance probe.

## Task

1. Add or update focused tests first to lock single-pass scan behavior and existing export semantics.
2. Refactor `_collect_benchmark_run()` to scan each run directory once while preserving ordering and fallback behavior.
3. Register a benchmark-export scoped probe in the PR-scoped performance registry so CI can compare base vs head for this path.
4. Run focused pytest for the touched scope.
5. Measure changed-scope coverage and require at least 95% automated coverage for the touched executable files before commit.
6. Run an explicit synthetic local performance probe with concrete numbers.
7. Run `git diff --check`, then commit, push, open a PR, wait for `pr-scoped-performance`, and enable squash auto-merge only after green CI.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_export.py`
- `services/mlx-worker-python/tests/test_benchmark_export.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- optional supporting script only if needed for the probe

## Verification

### Focused tests

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py
```

### Coverage

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_export.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py
```

### Performance probe

Run a synthetic benchmark-export probe that builds many run directories,
compares base vs head benchmark export collection, and records at least:

- `elapsed_ms_mean`
- `per_run_ms_mean`
- `run_directory_count`
- `result_file_count`

## Success Metrics

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local synthetic probe shows lower benchmark export collection latency on head vs base.
- The registered `pr-scoped-performance` probe passes in CI.
- `git diff --check` reports no issues.
