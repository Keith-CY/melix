# Benchmark store CSV row generator slice

## Scope

This Python-only performance slice is limited to `BenchmarkStore._write_jsonl_and_csv` in `services/mlx-worker-python/worker/productization/benchmark_store.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `benchmark-store-matrix-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries, and watches the benchmark store implementation, focused tests, PR-scoped performance tests, and `scripts/benchmark_store_probe.py`.

## Change

Avoid allocating a short-lived Python list for every CSV output row by passing a generator expression directly to `csv.writer.writerow`. JSONL serialization remains unchanged, and CSV field order continues to use the canonical field-name tuple.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe comparison.

## Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_counts_lines_without_read_text services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_counts_lines_without_read_text services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_store.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/benchmark_store_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/benchmark_store_probe.py
```
