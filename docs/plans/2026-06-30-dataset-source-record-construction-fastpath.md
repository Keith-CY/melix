# Dataset source record construction fast path

## Scope

This Python performance slice is limited to `worker.productization.dataset_preparation._record()` construction overhead. The hot probe builds many source records with empty metadata, so the slice avoids paying `dict(metadata)` for that common case while preserving copy isolation for non-empty metadata. It also keeps repeated hash and path lookups local within the same record-construction block without changing source IDs, URIs, content hashes, or byte accounting.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries. Linux local validation uses the registered commands; CI remains the registered PR-scoped performance validation source.

## Acceptance

- `_record()` still returns normalized text, stable hashes, byte accounting, and metadata isolated from caller mutation.
- Empty metadata records allocate a fresh empty dict without copying an already-empty mapping.
- Focused dataset ingest tests pass.
- Changed-scope coverage for the registered probe scope remains at or above 95%.
- The registered `dataset-source-records-scandir` probe shows a non-regressing or improved `record_elapsed_ms_mean` for the source-record construction phase.
