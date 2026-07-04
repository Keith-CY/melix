# Dataset record LF normalization fast path

## Scope

This Python-only performance slice targets
`worker.productization.dataset_preparation._normalize_line_endings` as used by
`_record(...)` and dataset ingest source record construction. The behavior remains
unchanged: LF-only text is returned unchanged, CRLF and lone CR line endings are
normalized to LF, and source record hashing/byte accounting continue to use the
normalized text.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the dataset preparation implementation,
focused ingest tests, PR-scoped performance tests, and
`scripts/dataset_source_records_probe.py`.

This slice updates the probe workload to exercise the common LF-only source record
case so base-vs-head CI can measure the normalization fast path directly through
the existing `record_elapsed_ms_*` metrics.

## Implementation plan

1. Add a focused regression test proving LF-only text remains unchanged while CRLF
   and lone CR inputs still normalize to LF.
2. Add a fast path that returns immediately when text contains no carriage return.
3. Keep the existing replacement logic for CR-containing text.
4. Run the registered focused tests, changed-scope coverage command, and the
   registered probe locally on Linux before opening the PR.

## Verification boundary

This slice is Python-only and locally verifiable on Linux. The PR-scoped GitHub
Actions performance workflow remains the merge gate for the registered probe
report.
