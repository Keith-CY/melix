# Dataset Quality Message Content Fast Path

## Scope

This Python-only performance slice is limited to the message-row branch inside
`worker.productization.dataset_preparation._append_sample_output_lengths(...)`.
The helper is used by `_quality_summary(...)` when building dataset version
quality summaries.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_quality_lengths_probe.py`

## Hypothesis

Dataset quality summaries mostly process `completion` rows, but the registered
probe also includes chat-message validation rows. The current message branch
checks `isinstance(item, dict)` before every content lookup. The expected hot
path uses dictionary message items, so reading `item.get(...)` directly and
falling back only for non-mapping items should preserve semantics while removing
one common-path type check per message item.

A pre-slice trial that switched completion rows to `try/except KeyError`
regressed the 31-sample Linux probe from `2.228684 ms` to `2.798706 ms`, so it
was rejected and reverted.

Baseline local probe on Linux before the accepted message-content fast path:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_DATASET_QUALITY_LENGTHS_SAMPLES=101 uv run --project services/mlx-worker-python python3 scripts/dataset_quality_lengths_probe.py
{"elapsed_ms_mean": 2.325885, "elapsed_ms_min": 2.149487, "elapsed_ms_p95": 2.597716, "mean_output_length": 51.999, "p95_output_length": 100.0, "row_count": 15000.0, "sample_count": 101.0, "train_row_count": 12000.0, "validation_row_count": 3000.0}
```

Accepted local probe on Linux after the message-content fast path:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_DATASET_QUALITY_LENGTHS_SAMPLES=101 uv run --project services/mlx-worker-python python3 scripts/dataset_quality_lengths_probe.py
{"elapsed_ms_mean": 2.141221, "elapsed_ms_min": 2.07063, "elapsed_ms_p95": 2.348198, "mean_output_length": 51.999, "p95_output_length": 100.0, "row_count": 15000.0, "sample_count": 101.0, "train_row_count": 12000.0, "validation_row_count": 3000.0}
```

Delta: `old_mean=2.325885 ms`, `new_mean=2.141221 ms`, `delta=-0.184664 ms`,
`speedup=1.0862x`.

## Verification Plan

1. Keep the registered `dataset-quality-lengths-chain` probe unchanged.
2. Extend focused behavior coverage for non-dict message items.
3. Run the registered focused tests.
4. Run changed-scope coverage for the touched Python/test/probe paths.
5. Run the registered probe locally on Linux and use GitHub Actions PR-scoped
   performance as the merge gate.
