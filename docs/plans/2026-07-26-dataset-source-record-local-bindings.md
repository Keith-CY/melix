# Dataset source record local bindings

## Scope

This Python-only performance slice targets
`worker.productization.dataset_preparation._record`, the hot helper that
materializes dataset ingest source records after source path discovery,
classification, and text reading have already completed.

Behavior remains unchanged: records keep the same `source_id`, `source_uri`,
`source_kind`, digest, byte-size accounting, text, and metadata semantics.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the dataset preparation implementation,
focused ingest tests, PR-scoped performance tests, and
`scripts/dataset_source_records_probe.py`.

## Implementation plan

1. Keep `_record` behavior and output shape unchanged.
2. Bind the content digest helper, source-id helper, and fspath result locally so
   the return literal avoids repeated global lookups on the per-record hot path.
3. Run the registered focused tests, changed-scope coverage command, and the
   registered probe locally on Linux before opening the PR.

## Verification boundary

This slice is Python-only and locally verifiable on Linux. The PR-scoped GitHub
Actions performance workflow remains the merge gate for the registered probe
report before merge.
