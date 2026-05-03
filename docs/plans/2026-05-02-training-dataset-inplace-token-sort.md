# Training dataset in-place token summary sort

## Goal

Reduce avoidable allocations in `services/mlx-worker-python/worker/model_ops/training_dataset.py` when building token summaries from temporary token-count lists.

## Constraints

- This slice is Linux-verifiable Python-only work under `services/mlx-worker-python`.
- The change must preserve the existing token-stat output schema and percentile semantics exactly.
- The affected path is already covered by the registered PR-scoped probe `training-dataset-token-percentiles-single-sort` in `infra/perf/pr_scoped_probes.json`.
- Keep the change limited to one coherent optimization slice plus focused regression tests.

## Proposed change

1. Extend `_summarize_token_values(...)` with an internal opt-in path that can sort the provided list in place.
2. Use that opt-in only from callers that pass freshly built temporary token-count lists inside:
   - `_build_quality_and_token_stats(...)`
   - `_collect_token_stats(...)`
3. Leave the default helper behavior non-mutating for any other direct callers.
4. Add focused tests that prove:
   - the default helper behavior still preserves caller ordering
   - the in-place fast path preserves summary values while sorting the temporary list

## Probe and success metrics

### Scoped CI probe

`training-dataset-token-percentiles-single-sort`

### Measurement path

The registered probe repeatedly calls `_build_quality_and_token_stats(samples, "prompt_completion")` on a large synthetic dataset and records:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- unchanged semantic guard rails such as `sample_count`, `duplicate_count`, and percentile fields

### Success metric

- Primary: lower `peak_bytes_mean` and/or `elapsed_ms_mean` versus `origin/main`
- Guard rails: unchanged semantic metrics from the existing probe output

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_training_dataset_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_training_dataset_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_training_dataset_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_training_dataset_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id training-dataset-token-percentiles-single-sort --base-repo /tmp/melix-training-dataset-base --head-repo "$PWD" --output /tmp/melix-training-dataset-probe.json
git diff --check
```