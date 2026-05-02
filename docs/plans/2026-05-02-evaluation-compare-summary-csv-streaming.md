# Evaluation compare summary CSV streaming

## Goal

Reduce peak memory in `EvaluationStore.persist_compare_result(...)` by streaming `evaluation-compare-summary.csv` rows directly to disk instead of building one giant CSV string in memory.

## Linux-only constraint

This cron run happens on Linux, so the slice must stay inside the Python worker and use Linux-verifiable tests, coverage, and local performance probes.

## Touched files

- `services/mlx-worker-python/worker/productization/evaluation_store.py`
- `services/mlx-worker-python/tests/test_evaluation_store.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Task

1. Add a streamed compare-summary CSV writer for `persist_compare_result(...)`.
2. Preserve the exact CSV header, row ordering, quoting, and adapter-lineage column behavior.
3. Add focused tests proving the persistence path does not fall back to `_compare_summary_csv(...)` and that the streaming writer emits the same bytes as the legacy builder.
4. Register a dedicated PR-scoped performance probe for the compare-summary path so CI measures the actual optimization path.

## Performance probe

- **Probe ID:** `evaluation-store-compare-summary-csv-streaming`
- **Path measured:** `EvaluationStore._write_compare_summary_csv(...)`
- **Synthetic workload:** write a compare-summary CSV for thousands of target summaries through the dedicated streaming writer, without sample-row persistence.
- **Metrics:**
  - `peak_bytes_mean` — primary metric, lower is better
  - `elapsed_ms_mean` — secondary metric, lower is better
  - `summary_count` and `csv_line_count` — correctness guard rails

## Success metrics

- Lower `peak_bytes_mean` versus `origin/main` on the dedicated compare-summary probe.
- No change to emitted CSV contents.
- Changed-scope automated coverage at or above 95% for the touched executable scope.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_compare_summary_probe

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_store_compare_summary_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/evaluation_store.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_evaluation_store_compare_summary_csv_streaming as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```