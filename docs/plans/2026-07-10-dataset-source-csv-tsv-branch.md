# Dataset source CSV/TSV suffix branch

## Scope

This Python-only performance slice is limited to dataset ingest source-kind
classification in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The prior lowercase fast path handled common `.csv` and `.tsv` names by slicing the
last four characters and checking tuple membership. The new slice keeps the same
last-character dispatch but compares the shared four-character suffix with direct
`==` checks so common structured-data names avoid the tuple-membership branch.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The entry
already has focused `test_command`, `coverage_command`, and `probe_command`
values for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

The probe reports source-tree traversal timing plus source-kind classification
metrics (`source_kind_elapsed_ms_mean`, `source_kind_elapsed_ms_min`, and
`source_kind_elapsed_ms_p95`).

## Optimization plan

1. Keep the existing lowercase suffix semantics for `.csv` and `.tsv`.
2. Replace tuple membership with direct suffix equality checks in the hot
   last-character branch.
3. Preserve fallback classification for uppercase or uncommon suffix spellings.
4. Run focused tests, changed-scope coverage, `git diff --check`, and the
   registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the final registered probe merge
   gate.

## Verification

- Focused dataset-ingest and PR-scoped performance tests pass.
- Changed-scope coverage for touched Python/test/probe files remains at or above
  95%.
- Local registered probe should improve or stay stable on
  `source_kind_elapsed_ms_mean`; CI remains the merge-gate source of truth for
  the registered probe report.
