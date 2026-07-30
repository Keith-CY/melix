# Dataset record SHA-256 local binding performance slice

## Scope

This Python-only performance slice is limited to `worker.productization.dataset_preparation._record()`.
Dataset ingest builds one source record per candidate file, and `_record()` currently resolves `hashlib.sha256` inside every record construction before hashing the source path. This slice keeps record semantics unchanged while reusing a module-level SHA-256 constructor binding for both source-id hashing and normalized text digesting.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The probe reports `record_elapsed_ms_*` for `_record()` construction plus source path iteration and source-kind classification metrics.

## Implementation plan

1. Add regression coverage asserting `_record()` source ids remain the first 16 hex characters of the SHA-256 digest of the UTF-8 path string.
2. Add a module-level SHA-256 constructor binding and use it in `_record()` and `_record_content_digest_and_size()`.
3. Run the registered focused test command, changed-scope coverage command, and the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## Validation notes

This slice is locally verifiable on Linux. No Swift runtime effect is claimed.
