# Homogeneous batch decode cache compatibility

The Swift text worker batches homogeneous decode requests only after the
backend proves that the candidate requests can safely share one model forward
pass.

## Context

Issue #1642 tracks the remaining release Gemma E4B serving gap against OMLX and
SwiftLM. The high-impact path is concurrent text decode where multiple requests
share the same loaded Swift MLX model, prompt length, and cache-compatible
forward-pass state.

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
- identical decode step size and prefill token
- text-only prepared state with matching prompt length
- compatible KV cache signatures across every layer

Sampling configuration, stop policy, seed, and output limits are sequence-local.
They do not participate in the forward-pass eligibility key. The backend creates
per-request decode parameters, logit processors, samplers, and max-token checks
for every row in the batch.

Compatible cache signatures include `KVCacheSimple`, `RotatingKVCache`, and the
worker-owned dense `PagedKVCache`. Simple and rotating layers require matching
type, offset, max size, state shape, and metadata. Paged layers require matching
block size, layer index, offset, per-block tensor shape and dtype, and metadata;
block IDs may differ because physical ownership is row-local.

The backend wraps simple and rotating batched caches with a
batch-position-aware adapter so per-row position offsets advance independently.
For paged layers it retains the original row cache objects and their leases,
splits each incoming K/V update by batch row, and concatenates the updated row
state for the attention call. Splitting or shrinking the cohort returns those
same row caches, preserving block ownership and copy-on-write history.

Unsupported cohorts fall back inside the batch event surface to the existing
single-request decode path. The worker must not emit synthetic batch-size-two
model evidence for unsupported cache layouts. Fallback summaries include a
typed `not_batchable` reason, such as
`not_batchable:cache_signature_unsupported`, so cache admission failures are
observable without treating them as request-loop aborts.

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
