# Evaluation Sample Probe Aggregation Optimization Plan

## Goal

Reduce redundant work in `EvaluationCore` when building evaluation result metrics by aggregating repeated sample probe mean calculations in a single pass instead of scanning the same sample tuple once per metric.

## Constraints

- Host verification is Linux-only.
- Keep the slice Python-only and locally verifiable.
- Preserve metric keys, units, rounding, and output values exactly.
- Keep the PR reviewable and limited to one coherent optimization slice.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Task Breakdown

### Task 1 — Single-pass evaluation sample probe aggregation

Implement a single-pass helper for the evaluation sample probe mean fields currently computed by repeated `_sample_probe_mean(...)` calls, then route the evaluation result metric assembly through that helper.

Requirements:
- Preserve existing metric names:
  - `sample_render_ms_mean`
  - `inference_ms_mean`
  - `extraction_ms_mean`
  - `validation_ms_mean`
  - `scoring_ms_mean`
  - `raw_response_chars_mean`
  - `extracted_result_chars_mean`
- Preserve `0.0` behavior for empty samples and missing/falsey field values.
- Preserve rounding to 4 decimal places.
- Add or update focused tests that prove the aggregated helper matches existing semantics and that the evaluation result path still emits the same metrics.
- Register a PR-scoped performance probe for this path so CI can compare base vs head on the same synthetic workload.

## Verification

### Focused tests

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_evaluation_core.py::test_sample_probe_means_aggregate_multiple_fields_in_one_pass \
  services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_executes_packaged_dataset_and_persists_result \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_probes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_sample_probe_aggregation_probe
```

### Changed-scope coverage

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_evaluation_core.py::test_sample_probe_means_aggregate_multiple_fields_in_one_pass \
  services/mlx-worker-python/tests/test_evaluation_core.py::test_run_local_suite_executes_packaged_dataset_and_persists_result \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_probes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_sample_probe_aggregation_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/evaluation_core.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py
```

### Performance probe

Use the registered PR-scoped probe and also run it locally:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_evaluation_sample_probe_aggregation as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```

### Hygiene

```bash
git diff --check
```