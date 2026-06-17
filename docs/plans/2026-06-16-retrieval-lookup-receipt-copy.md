# Retrieval lookup receipt-copy fast path

## Goal

Reduce receipt-copy overhead in `worker.runtime.retrieval_context.project_retrieval_lookup_result()` without changing payload or receipt isolation semantics.

## Scope

This Python-only performance slice is limited to:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- focused retrieval-context tests covered by the registered probe

No retrieval admission, duplicate-field handling, payload deep-copy behavior, or refusal policy changes are included.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Optimization slice

`_copy_receipts()` now copies flat receipt dictionaries with `receipt.copy()` instead of the generic `dict(receipt)` constructor. Receipt dictionaries remain shallow-copied, so callers still receive isolated receipt objects while avoiding extra constructor dispatch in the lookup-result copy path.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered probe command locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
