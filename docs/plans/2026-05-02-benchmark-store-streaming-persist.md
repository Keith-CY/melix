# Benchmark Store Streaming Persist Plan

## Goal

Reduce peak memory in `BenchmarkStore.persist_benchmark_matrix()` by eliminating full-batch tuple materialization of summary/request payload dicts while preserving artifact content, ordering, and per-row serialization semantics.

## Linux-only constraint

This slice is Python-only and will be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit performance probe. PR-scoped performance CI will be updated to measure this path on GitHub Actions.

## Touched files

- `services/mlx-worker-python/worker/productization/benchmark_store.py`
- `services/mlx-worker-python/tests/test_benchmark_store.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/benchmark_store_probe.py`

## Implementation approach

1. Refactor `persist_benchmark_matrix()` to stream row payloads into JSONL and CSV outputs without building whole `summary_payloads` / `request_payloads` tuples.
2. Keep each row's `to_dict()` call count at exactly once per persist.
3. Preserve exact output shapes and file ordering.
4. Register a PR-scoped performance probe for the benchmark-store path using a base-compatible `command_json` script.
5. Add focused regression tests for streamed writes and probe registration.

## Performance probe

Probe ID: `benchmark-store-matrix-streaming`

Metrics:
- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)

Synthetic workload:
- Build a benchmark matrix job with a large set of summary/request rows.
- Persist artifacts into a temporary directory.
- Record elapsed wall time and `tracemalloc` peak bytes.
- Ensure artifact line counts remain stable.

## Success metrics

- No behavior regressions in focused tests.
- Changed executable scope coverage >= 95%.
- Probe demonstrates reduced peak traced allocation versus `origin/main` while preserving artifact counts.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_benchmark_store_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_store.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/benchmark_store_probe.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/benchmark_store_probe.py`
- `git diff --check`
