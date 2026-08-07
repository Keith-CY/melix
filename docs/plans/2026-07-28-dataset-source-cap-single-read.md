# Dataset source capped-read single read slice

## Scope

This Python-only performance slice is limited to `worker.productization.dataset_preparation._read_source_text()` when dataset ingest has a positive source/read cap. The behavior remains unchanged: unbounded reads still use one full binary read, capped reads still reject payloads larger than the configured cap, and successful capped reads still decode the same UTF-8 text.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. This slice extends `scripts/dataset_source_records_probe.py` and the registry metrics with capped-read timings:

- `capped_read_elapsed_ms_mean`
- `capped_read_elapsed_ms_min`
- `capped_read_elapsed_ms_p95`

The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches the implementation, focused ingest tests, PR-scoped performance tests, and probe script.

## Plan

1. Add regression tests proving positive-cap reads use one bounded binary read and overflow detection still raises after reading `cap_bytes + 1` bytes.
2. Replace the capped chunk-accumulation loop with a single bounded `read(cap_bytes + 1)` and one length check.
3. Extend the registered dataset-source-records probe with capped-read metrics.
4. Run the focused registered tests, changed-scope coverage, and local registered probe on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
