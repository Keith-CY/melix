# Benchmark queue local binding scan slice

## Scope

This Python performance slice is limited to the benchmark queue record listing
hot path in `services/mlx-worker-python/worker/productization/benchmark_queue.py`.
It does not change queue record semantics, persistence format, or public return
shape.

## Linux verification boundary

The path is Python-only and is locally verifiable on Linux. Focused tests,
changed-scope coverage, and the registered PR-scoped probe must pass before the
PR is merged.

## Registered probe

The affected path is covered by the existing `benchmark-queue-decoded-record-cache`
entry in `infra/perf/pr_scoped_probes.json`. The registered entry includes
focused `test_command`, `coverage_command`, and `probe_command` values, and it
reports cold and warm queue scan timing plus JSON decode counts.

## Optimization hypothesis

`BenchmarkQueueStore.list_records()` executes a per-entry loop over queue JSON
files. The current loop repeatedly resolves instance/static/module attributes for
record loading, metadata-key construction, and regular-file checks. Binding these
callables once before the loop should reduce Python attribute lookup overhead
without weakening the existing stat reuse or decoded-record cache behavior.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_benchmark_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_benchmark_queue_cache_rejects_unexpected_record_count
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/benchmark_queue.py \
  services/mlx-worker-python/tests/test_benchmark_queue.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/melix_benchmark_queue_probe.py

git diff --check
```

## Success criteria

- Focused behavior and PR-scoped registry tests pass.
- Changed-scope coverage remains at least 95%.
- Local registered probe reports `warm_json_loads_mean == 0.0` and a lower warm
  scan mean than the baseline sample.
- Hosted PR-scoped performance CI validates the same registered probe before merge.
