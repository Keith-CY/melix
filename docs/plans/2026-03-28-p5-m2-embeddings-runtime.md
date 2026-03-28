# P5-M2 Embeddings Runtime

**Date:** 2026-03-28  
**Phase:** Phase 5, Milestone 2  
**Status:** In Progress  
**Owner:** Codex

## Goal

Activate the first real Python embedding worker path so Melix can load an embedding-class model and return stable vector outputs through `InferenceService.Embed`.

## Non-Goals

- No rerank runtime in this milestone.
- No control-plane `/v1/embeddings` endpoint yet.
- No model-operations jobs such as quantization, upload, or download.
- No attempt to make embedding execution share the Swift text hot path.

## Context

Phase 5 already introduced typed capability metadata and worker route classes in `P5-M1`. The next executable slice is worker-local embedding behavior. This milestone should stay inside the Python worker and provide:

- embedding model catalog coverage
- embedding model load lifecycle
- deterministic batch embedding output
- worker-side throughput probes and metrics evidence

This slice should keep the existing text runtime behavior unchanged.

## Performance Probes

The changed path must define and report:

- `embedding.embed_ms`
- `embedding.batch_size`
- `embedding.vector_dim`
- `embedding.rows_per_second`

The first metrics report can use a deterministic embedding backend. Real MLX embedding performance remains a later milestone.

## Work Plan

### Task 1: Add embedding runtime primitives

Introduce a dedicated deterministic embedding runtime for Python workers. It should expose model load, resident-byte estimate, and batch embedding operations with stable output.

### Task 2: Teach the registry about embedding models

Extend the worker registry so it can:

- resolve embedding-class models from the model catalog
- load embedding models without reusing the text runtime
- keep runtime stats and loaded-handle tracking consistent across text and embedding handles

### Task 3: Activate `InferenceService.Embed`

Replace the current structured `unimplemented` response with a working embedding path. Missing handles and wrong model classes must still return structured errors.

### Task 4: Verify worker behavior and capture metrics

Add test coverage for:

- loading the dev embedding model
- deterministic multi-row embeddings
- repeated-call stability
- wrong-handle and wrong-model-kind errors

Capture a small deterministic throughput report for the worker-local embedding path.

## Verification

Run at least:

```bash
make py-test
git diff --check
```

If the touched Python scope remains measurable, run coverage for the worker package and report the result.

## Acceptance Criteria

- `WorkerModelCatalog` exposes a dev embedding model.
- `RuntimeService.LoadModel` can load that embedding model successfully.
- `InferenceService.Embed` returns deterministic vectors for a loaded embedding model.
- Batch order is preserved.
- Missing handles and text-model handles return structured errors.
- The metrics report includes non-`N/A` deterministic embedding timings.

## Safe Exit

If the embedding runtime proves unstable, revert to the previous `unimplemented` path without disturbing the text generation flow or the typed capability metadata introduced in `P5-M1`.
