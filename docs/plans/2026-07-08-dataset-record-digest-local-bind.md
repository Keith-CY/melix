# Dataset record content digest cache

## Scope

This Python performance slice is limited to `worker.productization.dataset_preparation._record()` record materialization. Dataset ingest and probe fixtures can materialize many records with repeated normalized text; the previous hot path encoded the same normalized text and recomputed its content SHA-256 for every record even when only the source path changed.

This slice adds a bounded `lru_cache` helper for the normalized-text content digest and byte-size pair. `_record()` still computes the source-id hash from each path independently, keeps metadata copy isolation, and returns the same record schema. The cache is bounded to avoid unbounded retention while accelerating repeated normalized text bodies.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Verification plan

1. Run the registered focused test command for `dataset-source-records-scandir` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and keep coverage at or above 95%.
3. Run the registered probe command locally on Linux and compare against the pre-change baseline, focusing on `record_elapsed_ms_mean` and `record_elapsed_ms_p95` while ensuring file count, source-kind classification, and byte accounting remain unchanged.
4. Let GitHub Actions run the registered PR-scoped performance workflow before merging.

## Acceptance

- `_record()` preserves stable per-path `source_id`, `content_sha256`, `byte_size`, `source_uri`, and metadata copy semantics.
- Repeated normalized text records reuse the bounded digest/size cache without sharing path-derived identifiers.
- Focused dataset ingest and PR-scoped registry tests pass.
- Changed-scope coverage for the touched scope remains at or above the repository threshold.
- The registered `dataset-source-records-scandir` probe is non-regressing or improved for source record construction.
