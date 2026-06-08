# Dataset source-kind basename cache

## Slice

This Python performance slice is limited to dataset ingest source-kind classification in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry watches the dataset preparation implementation, focused ingest tests, PR-scoped performance tests, and `scripts/dataset_source_records_probe.py`; it includes focused `test_command`, `coverage_command`, and `probe_command` entries. Its metrics include `source_kind_elapsed_ms_mean`, `source_kind_elapsed_ms_min`, and `source_kind_elapsed_ms_p95` for the classification loop.

## Change

Keep source-kind semantics unchanged while splitting basename classification into `_source_kind_for_name(name)`, cached with `functools.lru_cache(maxsize=4096)`. `_source_kind(path)` now delegates to that helper with `path.name`, so repeated fixture/source basenames across ingest directories reuse the suffix classification result instead of re-running case normalization and suffix membership checks.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the CI merge gate for the registered probe.
