# P5-M3 Rerank Runtime

**Date:** 2026-03-28  
**Phase:** Phase 5, Milestone 3  
**Status:** In Progress  
**Owner:** Codex

## Goal

Activate the first real Python rerank worker path so Melix can load a rerank-class model and return stable ranked document scores through `InferenceService.Rerank`.

## Non-Goals

- No control-plane `/v1/rerank` endpoint yet.
- No model-operations jobs in this milestone.
- No cross-request batching or mixed-load scheduling logic yet.
- No attempt to reuse the embedding runtime for rerank semantics.

## Context

`P5-M2` introduced the first Python embedding runtime and verified that non-text worker classes can load and serve deterministic vector outputs. The next slice is rerank behavior with:

- rerank model catalog coverage
- rerank model load lifecycle
- stable score ordering and `top_k` enforcement
- worker-local latency probes

This milestone should keep text and embedding behavior unchanged.

## Performance Probes

The changed path must define and report:

- `rerank.rerank_ms`
- `rerank.document_count`
- `rerank.top_k`
- `rerank.docs_per_second`

## Work Plan

### Task 1: Add rerank runtime primitives

Introduce a deterministic rerank runtime for Python workers with model load, resident-byte estimate, and stable score generation.

### Task 2: Extend the registry for rerank models

Teach the worker registry to resolve and load rerank-class models without disturbing text or embedding model handling.

### Task 3: Activate `InferenceService.Rerank`

Replace the current structured `unimplemented` response with a working rerank path that:

- rejects missing handles
- rejects wrong model classes
- sorts scores descending
- honors `top_k`

### Task 4: Verify behavior and capture metrics

Add test coverage for:

- loading the dev rerank model
- stable ranking results
- `top_k` limiting
- missing-handle and wrong-model-kind errors

Capture a deterministic rerank latency report.

## Verification

Run at least:

```bash
make py-test
git diff --check
```

If the touched Python scope remains measurable, run coverage for the worker package and report the result.

## Acceptance Criteria

- `WorkerModelCatalog` exposes a dev rerank model.
- `RuntimeService.LoadModel` can load that rerank model successfully.
- `InferenceService.Rerank` returns deterministic descending scores.
- `top_k` is enforced without reordering mistakes.
- Missing handles and non-rerank handles return structured errors.
- The metrics report includes non-`N/A` deterministic rerank timings.

## Safe Exit

If rerank behavior proves unstable, revert to the previous `unimplemented` path without disturbing text or embedding runtime behavior.
