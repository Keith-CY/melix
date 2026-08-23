# Dataset Registry Split Inference Stem Rfind Performance

## Status

Accepted for one PR-scoped performance slice on 2026-08-23.

## Scope

This slice covers `services/mlx-worker-python/worker/dataset_registry/catalog.py`, specifically split/config inference called while building dataset registry snapshots.

## Optimization

Replace `filename.rsplit(".", 1)[0]` with a single `rfind(".")` plus slicing in `_inferred_split_and_config()`. The helper only needs the filename stem for split alias detection, so avoiding `rsplit()` list allocation keeps behavior equivalent for dataset paths while reducing per-file work in large snapshot scans.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `dataset-registry-snapshot-inference-single-pass` in `infra/perf/pr_scoped_probes.json`.

Focused validation uses:

- `test_command`: dataset registry tests plus PR-scoped probe selection/registry tests.
- `coverage_command`: focused coverage for `catalog.py`, dataset registry tests, PR-scoped performance tests, and `scripts/dataset_registry_snapshot_probe.py`.
- `probe_command`: `scripts/dataset_registry_snapshot_probe.py` with JSON metrics including `elapsed_ms_mean`, `peak_bytes_mean`, and file/sidecar counts.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe shows a lower `elapsed_ms_mean` on the changed implementation compared with `origin/main` under the same local Linux workload.
- CI PR-scoped performance workflow completes successfully before merge.
