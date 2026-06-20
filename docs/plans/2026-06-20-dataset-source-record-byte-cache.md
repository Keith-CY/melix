# Dataset Source Record Byte Cache Slice

## Scope

This Python-only performance slice is limited to dataset ingest record construction in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The implementation keeps source record semantics unchanged while reusing the normalized UTF-8 byte payload for both `content_sha256` and `byte_size` inside `_record(...)`. This removes one repeated `str.encode("utf-8")` call per source record without changing line-ending normalization, source ids, metadata copying, or structured/non-structured ingest behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Verification Plan

1. Run the new focused record-construction regression test locally on Linux.
2. Run the registered focused test command for `dataset-source-records-scandir` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally on Linux before pushing.
5. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Metrics

Use `scripts/dataset_source_records_probe.py` through the registered probe command. Primary metrics are `record_elapsed_ms_mean`, `record_elapsed_ms_min`, and `record_elapsed_ms_p95` for record construction; directory scan and source-kind classifier metrics remain informational for this slice.
