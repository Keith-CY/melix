# Retrieval Context Receipt Builder Local Binding Performance Slice

## Scope

This slice optimizes the registered `retrieval-context-projection-fastpath` hot path by binding the shared `untrusted_context_receipt()` helper once per projection call before tight direct-entry/store-record loops. The behavior is unchanged: valid retrieved document/image contexts still project the same user payloads, untrusted-context receipts, and refusal receipts.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`. The probe includes focused retrieval-context tests, changed-scope coverage, and `scripts/retrieval_context_projection_probe.py`, which reports direct projection, store-record projection, lookup payload copy, and lookup wrapper metrics.

## Verification plan

- Run the registered focused test command for retrieval-context behavior and PR-scoped probe coverage.
- Run the registered changed-scope coverage command.
- Run `scripts/retrieval_context_projection_probe.py` locally on Linux before and after the change and compare `optimized_elapsed_ms_mean` and `store_optimized_elapsed_ms_mean`.
- Rely on GitHub Actions PR-scoped performance workflow for the final registered CI probe report before merge.

## Expected outcome

Local binding removes a global helper lookup from each valid direct projection/store-record iteration. The improvement should be visible primarily in `optimized_elapsed_ms_mean` and `store_optimized_elapsed_ms_mean`; lookup-copy and lookup-wrapper metrics are expected to remain within normal noise because this slice does not change those paths.
