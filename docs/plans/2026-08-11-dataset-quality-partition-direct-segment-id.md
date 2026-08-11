# Dataset quality failed-partition direct segment-id lookup

This Python-only performance slice is limited to `worker.productization.dataset_preparation._partition_failed_segments(...)`.

## Scope

The dataset quality probe already covers the failed-segment partition path through the registered `dataset-quality-lengths-chain` PR-scoped probe. The slice keeps the existing output partition semantics while optimizing the common generated-segment shape where every segment carries a `segment_id` key.

## Registered Probe

- Probe id: `dataset-quality-lengths-chain`
- Watch path: `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- Local Linux validation uses the probe `probe_command` from `infra/perf/pr_scoped_probes.json`.

## Plan

1. Preserve behavior for empty failure IDs, duplicate failed IDs, duplicate segments, and segments without `segment_id`.
2. Use direct `segment["segment_id"]` membership in the common path so Python does not enter a per-row `try/except` block when all rows are normal generated segments.
3. Retain a fallback path for rare malformed segment dictionaries that lack `segment_id`.
4. Run focused tests, changed-scope coverage, and the registered local probe before opening the PR.

## Acceptance

Accept the slice only if focused behavior tests pass, changed-scope coverage remains at least 95%, and the registered local Linux probe shows a clear improvement for `failed_partition_elapsed_ms_mean` without unacceptable regression in the shared dataset quality metrics.
