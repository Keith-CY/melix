# Retrieval public receipt inline fast path

## Scope

This slice only touches the Python retrieval-context projection path in
`project_retrieval_contexts()` for complete `RetrievalContextEntry` objects and
`project_retrieval_store_records()` for complete store-record dictionaries with
already-public source IDs.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused retrieval-context tests, changed-scope coverage, and
`scripts/retrieval_context_projection_probe.py`. The direct projection metrics
(`optimized_elapsed_ms_mean`, `delta_ms`, and `speedup`) are the primary signal
for this slice.

## Plan

1. Preserve the existing non-public source ID redaction behavior by falling back
   to `untrusted_context_receipt()` whenever the normalized source ID is not
   already public.
2. Inline the receipt dictionary for public source IDs, which avoids the generic
   receipt builder's redundant redaction and segment-prefix checks on the common
   registered-probe path for direct entry projection and complete store records.
3. Add focused regression tests proving public IDs use the inline receipt path
   while existing non-public redaction coverage continues to protect fallback
   behavior.
4. Run focused retrieval-context tests, changed-scope coverage, and the
   registered projection probe locally on Linux before pushing.

## Metrics

Primary metric: `optimized_elapsed_ms_mean` from
`scripts/retrieval_context_projection_probe.py`.

Secondary guard metrics:

- `store_optimized_elapsed_ms_mean`
- `lookup_copy_optimized_elapsed_ms_mean`
- `lookup_records_optimized_elapsed_ms_mean`

The slice is acceptable only if the registered probe remains directionally
non-regressing and CI publishes a successful PR-scoped performance report.
