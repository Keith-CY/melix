# Issue 2604 Per-Sequence Sampler Batch Admission

Date: 2026-07-08

## Context

Issue #2604 tracks a continuous batching limitation in the Swift text worker:
decode cohorts currently require identical sampling configuration before they can
share a model forward pass. That is stricter than the execution contract needs.
Temperature, top-p, top-k, penalties, stop sequences, seeds, and per-request
output limits are sequence-local sampler policy. They should not block a shared
forward pass when the model, lane, acceleration path, prepared text state, and KV
cache shape are otherwise compatible.

The existing homogeneous batch decode ADR intentionally used same-sampling as a
safe first boundary. This plan narrows that boundary to the actual forward-pass
compatibility contract while keeping the Swift MLX backend as the final authority
for real batched execution.

## End-State Direction

Batch admission should be split into two explicit layers:

1. The worker coordinator builds cohorts from forward-pass compatibility only:
   loaded model handle, lane, acceleration mode/profile, decode step contract,
   prefill token contract, and any batch-safe cache class requirement that is
   known before entering the backend.
2. The backend validates runtime-only compatibility before executing a batched
   model step. It accepts only requests that share the same `ModelContainer`,
   baseline acceleration path for this slice, text-only prepared state, matching
   prompt length, and compatible KV-cache signatures.
3. Sampler state is sequence-local. Each request owns its own
   `GenerateParameters`, logit processor, sampler, stop policy, seed, and output
   token limit. Mixed sampler cohorts must never borrow the first request's
   processor, sampler, or max-token limit.
4. Unsupported cache classes and shape mismatches stay isolated. The backend
   must produce a typed `not_batchable` reason for unsupported cache signatures
   or other forward-pass rejections instead of silently aborting the batch surface
   or emitting synthetic batch-size evidence.

Cache contract matrix:

| Cache state | Batch contract |
| --- | --- |
| Plain `KVCacheSimple` | Batchable when layer count, offset, state shapes, and metadata match. |
| `RotatingKVCache` / sliding-window KV | Batchable when max size, offset, state shapes, and metadata match. |
| Quantized KV | Not batchable in this slice; emit a cache-signature reason and run per request. |
| Speculative / MTP state | Not batchable in this slice; keep baseline-only batch admission. |

## Implementation Slice

1. Add failing Swift worker tests for mixed-sampler batch decode:
   - two compatible requests with different sampling policies execute through one
     real batch path and report `decodeBatchSize == 2` / `modelEvalBatchSize == 2`;
   - per-sequence max-token limits remain isolated so one request can finish
     earlier without stopping its peer;
   - unsupported cache signatures fall back with a `not_batchable` cache reason.
2. Remove sampling-only fields from the coordinator eligibility key while keeping
   true forward-pass fields in the key.
3. Change the Swift MLX batch input to carry per-request decode parameters. Use
   each request's own parameters for processor creation, sampling, max-token
   checks, and argmax fast-path eligibility.
4. Replace the backend same-sampling guard with explicit forward-pass guards.
   Keep baseline acceleration, shared container, text-only state, prompt length,
   and cache signature checks.
5. Add minimal backend rejection reasons for fallback summaries so tests and PR
   evidence can distinguish cache incompatibility from real batch execution.
6. Update the homogeneous batch decode ADR to state that sampling is
   per-sequence and that cache reasons are observable.

## Performance Probes and Metrics

The changed path is measured by the existing Swift text decode batch metrics:

- `swift_text.decode_batch_size`
- `swift_text.decode_batch_size_max`
- `swift_text.model_eval_batch_size`
- `swift_text.model_eval_batch_size_max`
- `swift_text.decode_batch_observation_count`
- `swift_text.decode_batch_*_us`
- `swift_text.per_batch_output_token_count`
- `swift_text.per_batch_output_tokens_per_second`

The PR should include a scoped pre-commit performance report. If the local
registry selects the same-cohort batching probe for the touched files, it is the
primary performance signal; otherwise the PR evidence should state that the
scoped report did not select that probe and include the Swift worker tests as the
functional batch evidence.

## Verification Plan

- Run the focused red test before implementation.
- Run the focused Swift worker tests after implementation.
- Run `make swift-test`.
- Run the repository pre-commit hook or equivalent full local gate before commit,
  including the scoped performance report.
