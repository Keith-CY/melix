# Dataset Record Normalized Text Fast Path

## Scope

This Python-only performance slice is limited to dataset ingest record construction in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`. It keeps
source discovery, source-kind classification, structured-data row expansion, hashing,
and metadata semantics unchanged.

## Registered Probe

Registered PR-scoped probe: `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`.

The probe already has focused `test_command`, `coverage_command`, and
`probe_command` entries covering `dataset_preparation.py`, the dataset ingest tests,
and `scripts/dataset_source_records_probe.py`. This slice extends the registered
metrics list with the probe's existing record-construction timings:

- `record_elapsed_ms_mean`
- `record_elapsed_ms_min`
- `record_elapsed_ms_p95`

## Implementation Plan

1. Add a regression test proving `_record(..., normalized=True)` does not re-run
   line-ending normalization for already-normalized text.
2. Have the non-structured source ingest path normalize text once, then pass the
   pre-normalized text into `_record` with the explicit fast-path flag.
3. Keep `_record` default behavior unchanged for structured rows and direct callers.
4. Run the focused registered tests, changed-scope coverage, and the registered
   probe locally on Linux before opening the PR.

## Success Criteria

- Focused dataset ingest and PR-scoped performance tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered local probe shows an improved or neutral `record_elapsed_ms_mean`
  without regressing the broader `elapsed_ms_mean` beyond probe noise.
- GitHub Actions PR-scoped performance completes successfully before merge.
