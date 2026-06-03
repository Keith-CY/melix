# Dataset Quality Row Loop Split Performance Slice

## Scope

Optimize one Python hot path in `worker.productization.dataset_preparation._append_sample_output_lengths(...)`, used by `_quality_summary(...)` while summarizing generated dataset versions.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for `services/mlx-worker-python/worker/productization/dataset_preparation.py`, `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`, `services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and `scripts/dataset_quality_lengths_probe.py`.

## Hypothesis

The quality summary path walks train and validation rows to collect output lengths. The current helper iterates over a temporary `(train_rows, validation_rows)` tuple and enters a nested row loop for both partitions. Splitting that outer partition loop into two direct row loops preserves output ordering and behavior while removing one level of loop dispatch from this frequently replayed summary path.

A rejected pre-slice trial bound `isinstance`, `dict`, `list`, and `len` locally; it raised the 9-sample mean from `2.498558` ms to `2.862005` ms and was not kept.

Baseline local probe on Linux before the accepted row-loop split:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_DATASET_QUALITY_LENGTHS_SAMPLES=21 uv run --project services/mlx-worker-python python3 scripts/dataset_quality_lengths_probe.py
{"elapsed_ms_mean": 2.510334, "elapsed_ms_min": 2.265901, "elapsed_ms_p95": 2.875164, "mean_output_length": 51.999, "p95_output_length": 100.0, "row_count": 15000.0, "sample_count": 21.0, "train_row_count": 12000.0, "validation_row_count": 3000.0}
```

Accepted local probe on Linux after the row-loop split:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_DATASET_QUALITY_LENGTHS_SAMPLES=21 uv run --project services/mlx-worker-python python3 scripts/dataset_quality_lengths_probe.py
{"elapsed_ms_mean": 2.260303, "elapsed_ms_min": 2.148971, "elapsed_ms_p95": 2.540818, "mean_output_length": 51.999, "p95_output_length": 100.0, "row_count": 15000.0, "sample_count": 21.0, "train_row_count": 12000.0, "validation_row_count": 3000.0}
```

Delta: `old_mean=2.510334 ms`, `new_mean=2.260303 ms`, `delta=-0.250031 ms`, `speedup=1.1106x`.

## Verification Plan

1. Keep the registered probe unchanged and scoped to `dataset-quality-lengths-chain`.
2. Run the focused regression tests from the registered probe.
3. Run changed-scope coverage for the touched path.
4. Run the registered probe locally on Linux and compare against the baseline above.
5. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.
