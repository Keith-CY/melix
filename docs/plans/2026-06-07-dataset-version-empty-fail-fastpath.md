# Dataset version empty failure fast path

## Scope

This Python performance slice is limited to `prepare_dataset_version(...)` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The common dataset-version path has no failed segment ids. The existing code
still built a `set` and scanned the full segment list twice to derive successful
and failed segment partitions.

This slice preserves output artifacts and failure semantics while adding an
explicit no-fail fast path that reuses the already-loaded segment list and avoids
partition scans when `fail_segment_ids` is empty.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for dataset version/quality behavior. The probe exercises
dataset-version generation with many successful rows, so the empty failure-id
partition fast path is measured by the existing registered probe.

## Verification plan

1. Add focused regression coverage for the partition helper so the empty-failure
   path returns the existing successful segment list and produces no failed
   segment rows, while non-empty failure ids retain the existing partition
   behavior.
2. Implement the single fast path in the dataset-version partition step.
3. Run the registered focused test command for `dataset-quality-lengths-chain`.
4. Run the registered changed-scope coverage command.
5. Run the registered probe locally on Linux and compare against `origin/main`
   using `scripts/pr_scoped_performance_run.py`.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.

## 2026-06-27 follow-up: failed partition single pass

The next focused slice keeps the same `prepare_dataset_version(...)` boundary and
registered `dataset-quality-lengths-chain` probe, but targets the non-empty
`fail_segment_ids` path. The empty-failure fast path already returns the original
segment list without scanning. For non-empty failure ids, `_partition_failed_segments(...)`
still preserves duplicate failed ids and output order, but can partition
successful and failed segments in one scan instead of two list-comprehension
passes over the same segment list.

The registered probe remains the validation gate. This follow-up extends
`scripts/dataset_quality_lengths_probe.py` with failed-partition metrics so CI
and local Linux runs report `failed_partition_elapsed_ms_*` together with the
existing quality-length metrics.

## 2026-07-07 follow-up: cached failed id set

This slice keeps the same `prepare_dataset_version(...)` boundary and registered
`dataset-quality-lengths-chain` probe. It targets repeated calls to
`_partition_failed_segments(...)` with the same non-empty `fail_segment_ids`
tuple, as exercised by the registered failed-partition probe samples. The helper
now reuses a small LRU-cached `frozenset` for the failed id membership table,
preserving duplicate segment output semantics while avoiding repeated set
construction across measurements and repeated dataset-version retries.

Validation remains Python-only and locally verifiable on Linux through the
registered focused tests, changed-scope coverage command, and local PR-scoped
performance probe comparison against `origin/main`.
