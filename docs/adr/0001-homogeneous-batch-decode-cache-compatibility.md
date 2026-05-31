# Homogeneous batch decode cache compatibility

The Swift text worker batches homogeneous decode requests only after the
backend proves that the candidate requests can safely share one model forward
pass.

## Context

Issue #1642 tracks the remaining release Gemma E4B serving gap against OMLX and
SwiftLM. The high-impact path is concurrent text decode where multiple requests
share the same loaded Swift MLX model, sampling policy, prompt length, and
output limits.

Batch decode requires combining per-request KV caches into a batched cache.
That is only correct when every request has the same cache layout and the same
sequence offsets. Swift MLX models may use different cache implementations,
including `KVCacheSimple` and `RotatingKVCache`.

## Decision

The worker-local coordinator may form a homogeneous decode cohort, but the
Swift MLX backend remains the final authority for whether the cohort can execute
as a real batched model step.

The backend batch path accepts only requests that share:

- the same loaded `ModelContainer`
- baseline decode mode
- identical sampling configuration, output limits, decode step size, and
  prefill token
- text-only prepared state with matching prompt length
- compatible KV cache signatures across every layer

Compatible cache signatures include `KVCacheSimple` and `RotatingKVCache`
layers when the type, offset, max size, state shape, and metadata match. The
backend wraps the batched cache with a batch-position-aware adapter so per-row
position offsets advance independently during decode.

Unsupported cohorts fall back inside the batch event surface to the existing
single-request decode path. The worker must not emit synthetic batch-size-two
model evidence for unsupported cache layouts.

## Consequences

Benchmark and metrics evidence can distinguish three states:

- scheduler admission formed a cohort
- worker decode formed an eligible homogeneous batch
- the Swift MLX backend actually executed model steps with batch size greater
  than one

This keeps scheduler-level batching evidence separate from real model execution
evidence. It also keeps sliding-window models eligible only when their prepared
caches have a matching shape and metadata; otherwise they take the existing
singleton fallback path.
