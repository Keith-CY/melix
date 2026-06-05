# Dataset source kind dotted suffix fast path

## Scope

This Python-only performance slice is limited to `worker.productization.dataset_preparation._source_kind`.
The behavior remains unchanged: dataset ingest still classifies text, extracted PDF/DOCX text, markdown,
code, structured data, and unsupported source file names the same way.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. The probe already has focused `test_command`, `coverage_command`, and
`probe_command` entries and measures both source file traversal and `_source_kind` classification latency.

## Plan

1. Keep the existing `os.scandir` traversal unchanged.
2. For source kind classification, preserve the case-sensitive common lowercase `.txt`/`.text` fast path.
3. On mixed-case or other suffixes, lower only the final dotted suffix instead of the whole filename; lower the stem only for mixed-case `.txt` extracted PDF/DOCX detection.
4. Verify with focused pytest, changed-scope coverage, and the registered local Linux probe.
5. Use PR-scoped performance CI as the merge gate.

## Metrics

Linux-local metrics will be captured with `scripts/dataset_source_records_probe.py`; GitHub Actions PR-scoped
performance output remains the registered base-vs-head validation source.
