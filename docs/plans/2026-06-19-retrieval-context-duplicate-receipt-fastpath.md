# Retrieval Context Duplicate Receipt Fast Path

## Linux-only constraint

This slice is Python worker runtime code and can be verified locally on Linux with focused tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Optimization

`worker.runtime.retrieval_context.project_retrieval_contexts()` and `project_retrieval_store_records()` already have fast paths for complete retrieval entries and store records. Before this slice, duplicate `source_field` entries still built a full included untrusted-context receipt and then converted it into a duplicate refusal receipt.

This slice keeps duplicate-refusal semantics unchanged while constructing duplicate refusal receipts directly from the normalized fields. The hot path avoids the intermediate included receipt allocation for duplicate projections and preserves the existing included receipt path for accepted entries.

## Registered probe

Existing registered probe: `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe already has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/worker/runtime/untrusted_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

This slice extends the probe metrics with a duplicate-entry projection scenario so the registered CI report captures the optimized duplicate-refusal path.

## Verification plan

Run the registered focused tests, changed-scope coverage, and local registered probe before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.
