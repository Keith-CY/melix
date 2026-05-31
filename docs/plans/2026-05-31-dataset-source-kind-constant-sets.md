# Dataset Source Kind Constant Suffix Sets

## Scope

Optimize one Python hot path in dataset ingest: `_source_kind()` classification for source files discovered by `worker.productization.dataset_preparation._iter_source_records()`.

The previous suffix fast path still allocated three literal `set` objects on every non-`.txt` / non-`.text` classification call. This slice preserves accepted source-kind behavior while hoisting those suffix membership tables to module-level immutable `frozenset` constants.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries. The local Linux probe reports:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `elapsed_ms_p95`
- `file_count_mean`

## Plan

1. Reuse existing source-kind behavior coverage for uppercase compound `.PDF.TXT`, `.DOCX.txt`, code, structured-data, and unsupported suffix cases.
2. Hoist markdown/code/structured-data suffix membership tables from per-call literals to module-level immutable constants.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
