# Retrieval Single-Field Projection Item Fast Path

## Goal

Reduce one redundant mapping lookup in `worker.runtime.retrieval_context.project_retrieval_contexts(...)` when a fallback admission projects exactly one payload field.

## Scope

This slice is Python-only and limited to the retrieval-context projection path plus focused regression coverage. It does not change prompt-context admission semantics, receipt redaction, store-record projection, lookup wrapper metadata handling, generated protocol artifacts, or Swift/macOS runtime behavior.

## Registered Probe

Registered PR-scoped probe: `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The registry entry already has focused `test_command`, `coverage_command`, and `probe_command` entries and covers the retrieval context projection path. Relevant metrics include:

- `optimized_elapsed_ms_mean` — lower is better for context projection.
- `store_optimized_elapsed_ms_mean` — lower is better for store projection guard coverage.
- `lookup_copy_optimized_elapsed_ms_mean` — lower is better for lookup payload copy coverage.
- `lookup_records_optimized_elapsed_ms_mean` and `lookup_records_optimized_get_calls_mean` — lower is better for lookup metadata records.

## Implementation Plan

1. Keep existing retrieval-context projection behavior intact.
2. For the single-field admission branch, read `(source_field, payload)` from `admission_payload.items()` once instead of iterating keys and then indexing the same mapping.
3. Add regression coverage proving the single-field branch projects the same payload without calling `__getitem__` on the admission payload mapping.
4. Reuse the registered retrieval-context projection probe for local Linux performance validation.

## Success Criteria

- Focused retrieval-context tests pass.
- Changed-scope coverage for touched files is at least 95%.
- The registered local probe shows a clear non-regression or improvement for `optimized_elapsed_ms_mean`.
- `git diff --check` passes.
