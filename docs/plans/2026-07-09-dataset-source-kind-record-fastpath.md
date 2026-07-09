# Dataset Source Kind and Record Fast Path Slice

## Scope

This Python performance slice is limited to the dataset ingest source-record hot path in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.

The slice keeps dataset ingest behavior unchanged while trimming per-file overhead in the
registered source-record probe:

- use direct `str.endswith(...)` checks for the common lowercase source suffix fast path;
- avoid rebinding `hashlib.sha256` for each `_record(...)` call before computing the
  source-id digest.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry
includes focused `test_command`, `coverage_command`, and `probe_command` commands and
watches this source file, `test_dataset_preparation_ingest.py`,
`test_pr_scoped_performance.py`, and `scripts/dataset_source_records_probe.py`.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered probe on
Linux before opening the PR. The probe reports path discovery, source-kind classification,
and record materialization timings for a 7k-file synthetic source tree.

Baseline sampled locally before the change:

```text
elapsed_ms_mean=12.051951822782444
source_kind_elapsed_ms_mean=19.16712398683144
record_elapsed_ms_mean=17.576634539926257
```

Post-change sampled locally three times:

```text
run1 elapsed_ms_mean=11.367001459637487 source_kind_elapsed_ms_mean=18.949219819412313 record_elapsed_ms_mean=18.316107913216744
run2 elapsed_ms_mean=11.179960459809411 source_kind_elapsed_ms_mean=17.782539912414823 record_elapsed_ms_mean=17.2133029978299
run3 elapsed_ms_mean=11.004839457613839 source_kind_elapsed_ms_mean=17.584661275825717 record_elapsed_ms_mean=16.922688185745344
```

Decision: accept only if focused tests and changed-scope coverage pass and the registered
CI probe also completes successfully without an in-scope regression.
