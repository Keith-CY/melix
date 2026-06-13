# Retrieval Store Projection Direct Admission Slice

## Context

The `retrieval-context-projection-fastpath` PR-scoped probe covers the retrieval context projection hot path in `services/mlx-worker-python/worker/runtime/retrieval_context.py`, including both direct entry projection and persisted retrieval store record projection.

The current store-record path validates records, materializes a list of `RetrievalContextEntry` objects, and then re-enters `project_retrieval_contexts()`. That preserves behavior but adds a second pass and transient entry list allocation for already-normalized store records.

## Slice

Optimize only `project_retrieval_store_records()` by projecting valid store records directly through `_admit_context()` and the shared admission projection helper. Preserve the existing refusal ordering contract: store-record wrapper refusals remain before projection/admission refusals.

## Probe

Registered probe: `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

Required focused commands:

- focused tests from the registered `test_command`
- changed-scope coverage from the registered `coverage_command`
- local Linux probe from the registered `probe_command`

## Boundary

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
