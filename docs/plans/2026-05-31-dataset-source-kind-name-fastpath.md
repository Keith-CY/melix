# Dataset source-kind name fast path

## Goal

Optimize the Python dataset-ingest source-kind classifier in
`services/mlx-worker-python/worker/productization/dataset_preparation.py` by
avoiding repeated `Path.suffix` work on the hot per-file classification path.

## Scope

This is a Linux-verifiable Python performance slice. It changes only the source
kind suffix classifier and the existing `dataset-source-records-scandir`
PR-scoped probe so the registered probe reports classifier timing in addition
to source-file discovery timing.

## Registered Probe

The affected path is covered by `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. This slice extends the existing probe with:

- `source_kind_elapsed_ms_mean`
- `source_kind_elapsed_ms_min`
- `source_kind_elapsed_ms_p95`

The existing focused `test_command`, `coverage_command`, and `probe_command`
remain attached to the same registry entry.

## Implementation Plan

1. Preserve the current source-kind behavior for compound `.pdf.txt` and
   `.docx.txt`, ordinary text, markdown, code, structured data, and unsupported
   extensionless/archive names.
2. Classify from one lower-cased filename string and a cheap `rpartition('.')`
   fallback instead of constructing `Path.suffix`.
3. Extend the registered local probe and probe tests so CI validates the new
   classifier metrics.
4. Run focused tests, changed-scope coverage, and the registered probe locally
   on Linux before pushing.

## Validation Boundary

No Swift path is changed. Local Linux validation is sufficient for behavior,
coverage, and the registered Python probe; GitHub Actions remains the merge
source of truth.
