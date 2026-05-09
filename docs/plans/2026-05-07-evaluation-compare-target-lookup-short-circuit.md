# Evaluation Compare Target Lookup Short-Circuit Plan

## Goal

Reduce redundant registry work in evaluation compare setup by stopping loaded-model scans once every requested comparison target has been resolved.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified locally on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- `services/mlx-worker-python/tests/test_evaluation_compare.py`
- `scripts/evaluation_compare_target_lookup_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Implementation approach

`resolve_compare_target_models(...)` currently builds a full `model_id -> loaded_model` map by calling `registry.get_loaded_model(...)` for every loaded handle, even when a compare request only targets one or a few models that appear early in the loaded registry.

The optimized path keeps the caller's target order for return/error behavior, tracks an internal `remaining_targets` set, stores only requested target models, and breaks the scan once all targets are found. If any target is missing, it still scans all handles before raising the same `ValueError` shape.

## Performance probe

Probe ID: `evaluation-compare-target-lookup-short-circuit`

Synthetic workload:

- 10,000 loaded model handles
- 3 requested target IDs placed first
- 400 repeated resolutions per sample
- 5 samples

Metrics:

- `elapsed_ms_mean` — lower is better
- `get_loaded_model_calls_mean` — lower is better and should drop from ~10,000 calls per lookup on `origin/main` to 3 calls per lookup on the branch

## Success metrics

- Focused tests pass for found, ordering, missing, and `None`/empty loaded-model cases.
- Changed-scope coverage for touched executable Python files is >=95%.
- Local base-vs-head probe shows identical target resolution checksum and materially lower registry calls/elapsed time.
- PR-scoped performance CI runs the registered probe and validates the same metrics.
