# Retrieval store refusal list elision

This Python-only performance slice is limited to `worker.runtime.retrieval_context.project_retrieval_store_records`.

## Scope

The hot path projects retrieval store records into prompt payloads. The common valid-record path usually has no store-level or projection-level refusal receipts, but the function still built a fresh combined list with starred unpacking at return time.

This slice keeps the existing projection behavior while reusing the store-refusal accumulator as the return list and only extending it when projection refusals exist. No admission, duplicate detection, payload copy, or receipt-copy semantics change.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `scripts/retrieval_context_projection_probe.py`

## Local verification plan

Run on Linux before opening the PR:

1. Focused retrieval-context tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. The registered probe command locally with repeated samples.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
