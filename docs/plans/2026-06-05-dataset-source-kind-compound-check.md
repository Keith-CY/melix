# Dataset Source Kind Compound Check Fast Path

## Scope

Optimize one Python hot path in dataset ingest: `_source_kind()` classification for `.txt` source files discovered by `worker.productization.dataset_preparation._iter_source_records()`.

The previous suffix fast path already avoided building `Path.suffixes`, but lowercase `.txt` candidates still performed full `.endswith(".pdf.txt")` and `.endswith(".docx.txt")` checks before the direct compound-suffix slice checks. This slice removes those redundant full-suffix checks and keeps the single direct slice checks as the source of truth for `.pdf.txt` and `.docx.txt` classification.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries. The local Linux probe reports:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `elapsed_ms_p95`
- `source_kind_elapsed_ms_mean`
- `source_kind_elapsed_ms_min`
- `source_kind_elapsed_ms_p95`
- `file_count_mean`

## Plan

1. Keep the existing source-kind behavior coverage for lowercase and mixed-case `.pdf.txt`, `.docx.txt`, `.txt`, `.text`, code, structured-data, and unsupported names.
2. Remove redundant compound `.endswith(...)` checks from the lowercase `.txt` path and use the already-present direct slice checks instead.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
