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

This follow-up slice keeps the same registered probe and adds a single-field payload fast path for the common `PromptContextAdmission` shape. Single-field admissions can check duplicate membership once and assign directly into the projected payload, while multi-field admissions continue to use the existing full duplicate-field scan and `dict.update()` path.

This follow-up narrows receipt-copy overhead by binding `dict.copy` directly for projected receipt copies. The loop still produces a fresh shallow copy for each receipt, preserving the existing object isolation boundary while avoiding the generic `dict(receipt)` constructor path.

This slice adds a single-receipt append fast path for the common admission shape emitted by retrieval entries. Multi-receipt admissions still copy every receipt through the existing loop, while the one-receipt case avoids setting up a per-receipt loop iterator.

This follow-up adds fast paths for valid store-record projection in `project_retrieval_store_records()`. The store bridge now skips the generic `Mapping` ABC check for exact `dict` records, binds loop-stable append/refusal helpers once, and returns the already isolated `project_retrieval_contexts()` projection directly when no malformed top-level records are present. Mapping subclasses and mixed valid/malformed records keep the existing defensive validation and refusal-copy path.

The registered `retrieval-context-projection-fastpath` probe is extended with store-record projection metrics so the store bridge fast path is measured by the same PR-scoped performance gate.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and registered probe command locally on Linux before opening the PR. The PR-scoped performance workflow remains the authoritative CI validation source after push.
