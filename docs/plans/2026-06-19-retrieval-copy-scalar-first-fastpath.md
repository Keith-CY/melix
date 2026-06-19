# Retrieval lookup payload tuple-three copy fast path

## Scope

This slice only touches the Python retrieval-context payload copy path used by
`project_retrieval_lookup_result()` when it clones projected lookup payloads for
prompt assembly.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused retrieval-context tests, changed-scope coverage, and
`scripts/retrieval_context_projection_probe.py`. The probe reports direct
projection, store-record projection, lookup payload copy, and lookup wrapper
metrics.

## Plan

1. Preserve behavior for scalar, `None`, list, tuple, dict, and fallback
   deepcopy payload values with an explicit regression test.
2. Keep the `None` guard ahead of exact type checks after CI showed the earlier
   scalar-first branch ordering regressed the registered retrieval probe.
3. Prioritize the three-item tuple branch in `_copy_payload_value()`, matching
   the lookup metadata label shape exercised by the registered projection probe.
4. Run focused retrieval-context tests, changed-scope coverage, and the
   registered projection probe locally on Linux before updating the PR.

## Metrics

Primary metric: `lookup_copy_optimized_elapsed_ms_mean` from
`scripts/retrieval_context_projection_probe.py`.

Secondary guard metrics:

- `optimized_elapsed_ms_mean`
- `store_optimized_elapsed_ms_mean`
- `lookup_records_optimized_elapsed_ms_mean`

The slice is acceptable only if the registered probe remains directionally
non-regressing and CI publishes a successful PR-scoped performance report. The
initial scalar-first branch order attempt was rejected by CI because it produced
a direct registered-probe regression; the accepted candidate keeps that guard
order and only reorders the tuple length checks.
