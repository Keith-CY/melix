# Evaluation Store Samples CSV Streaming Optimization Plan

## Goal

Reduce peak memory and redundant large-string assembly in `EvaluationStore.persist_result(...)` by streaming `evaluation-samples.csv` writes instead of building the full CSV payload in memory before writing it to disk.

## Linux-Only Constraint

This slice is limited to the Python worker evaluation artifact writer, its focused tests, and the PR-scoped performance harness so it can be fully verified on Linux without relying on macOS or Swift-only execution paths.

## Touched Files

- `services/mlx-worker-python/worker/productization/evaluation_store.py`
- `services/mlx-worker-python/tests/test_evaluation_store.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

- Add a streamed CSV writer for evaluation samples that writes the header and each row directly to the file handle.
- Route `persist_result(...)` through the streamed writer for `evaluation-samples.csv` while preserving the existing CSV schema and quoting behavior.
- Keep `_samples_csv(...)` behavior intact for existing direct callers/tests.
- Register a PR-scoped performance probe for the evaluation-store sample-artifact path.
- Add focused regression tests for the streamed writer, the `persist_result(...)` fast path, and the new probe wiring.

## Performance Probe

Measure `EvaluationStore.persist_result(...)` on a synthetic large evaluation run that persists JSON, JSONL, and sample CSV artifacts for a large sample tuple. Record:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `sample_count`

Compare the probe on `origin/main` vs the branch implementation through the PR-scoped performance harness.

## Success Metrics

- Persisted artifact contents and CSV quoting remain unchanged.
- Changed executable scope coverage is at least 95%.
- Local probe shows lower peak traced allocation for the large sample persistence path.
- The new registered PR-scoped CI probe selects this path and can compare `origin/main` against the branch implementation.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_probe`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_store_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_probe && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `git diff --check`
- Local old-vs-new evaluation-store sample persistence probe against `origin/main`
