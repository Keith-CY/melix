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
