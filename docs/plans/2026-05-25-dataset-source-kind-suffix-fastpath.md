# Dataset Source Kind Suffix Fast Path

## Scope

Optimize one Python hot path in dataset ingest: `_source_kind()` classification for source files discovered by `worker.productization.dataset_preparation._iter_source_records()`.

The previous implementation built and lowercased the full `Path.suffixes` list for every candidate file, even though dataset ingest only needs the final suffix plus two compound extracted-text cases (`.pdf.txt` and `.docx.txt`). This slice preserves classification behavior while reading `Path.suffix` once and checking the lowered filename only for `.txt` files.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries. The local Linux probe reports:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `elapsed_ms_p95`
- `file_count_mean`

## Plan

1. Add focused behavior coverage for source-kind suffix classification, including uppercase compound `.PDF.TXT` and `.DOCX.txt` cases.
2. Replace full suffix-list construction with a single final-suffix fast path and compound `.txt` filename checks.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.

## 2026-07-10 follow-up: path materialization comprehension

The `dataset-source-records-scandir` registered probe also covers the source-file
path discovery helper `_iter_source_file_paths()`. After the scandir traversal
collects and sorts file path strings, the helper materializes `Path` objects for
callers. This follow-up keeps traversal, sorting, symlink, and error-tolerance
semantics unchanged while using an explicit list comprehension instead of
`list(map(Path, ...))` for the final materialization step.

Validation remains the registered focused test command, changed-scope coverage
command, and local Linux `dataset-source-records-scandir` probe, with GitHub
Actions PR-scoped performance as the merge gate.
