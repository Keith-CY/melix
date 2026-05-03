# BenchmarkStore write coalescing plan

## Goal

Reduce per-row overhead in `BenchmarkStore._write_jsonl_and_csv()` for benchmark matrix artifact persistence by minimizing redundant work inside the hot loop while preserving output bytes, row ordering, and one-serialization-per-row behavior.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be fully verified from this Linux host without touching macOS/Swift surfaces.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_store.py`
- `services/mlx-worker-python/tests/test_benchmark_store.py`

## Optimization hypothesis

The current writer loop does extra per-row work:

1. JSONL output must stay coalesced to one write per row.
2. The loop should avoid repeated hot callables and should hand CSV row emission to `csv.writerows()` instead of calling `writerow()` once per Python row.

Coalescing the JSONL write, binding hot loop helpers locally, and using `csv.writerows()` over a streaming generator should reduce Python overhead on large benchmark matrix persists without changing semantics.

## Performance probe

Use the existing scoped probe script:

- `scripts/benchmark_store_probe.py`
- registered scoped CI probe: `benchmark-store-matrix-streaming`

Primary local success signal:

- lower `elapsed_ms_mean` in the local probe
- preserve row counts and artifact structure
- no regression in `peak_bytes_mean`

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_store.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/benchmark_store_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/benchmark_store_probe.py

git diff --check
```

## Success criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe reports concrete metrics and shows the optimized path is not worse for the measured hot path.
- Existing scoped CI probe `benchmark-store-matrix-streaming` can validate the same path in PR CI.
