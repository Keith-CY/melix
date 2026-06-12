# Retrieval context projection local bindings performance slice

## Goal

Reduce per-entry interpreter overhead in `project_retrieval_contexts()` without changing retrieval prompt-context admission semantics.

## Scope

This Python-only slice is limited to:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- focused retrieval-context tests and the registered PR-scoped performance probe

The implementation keeps payload projection, duplicate-field refusal handling, and receipt-copying behavior unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Optimization Slice

Bind loop-stable helpers (`_admit_entry`, `_duplicate_projection_receipt`, list `extend`, payload `update`, and `dict`) once before the projection loop. This avoids repeated global and attribute lookups while keeping the same object-copy boundaries for receipts and the same duplicate-field refusal policy.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and registered probe command locally on Linux before opening the PR. The PR-scoped performance workflow remains the authoritative CI validation source after push.
