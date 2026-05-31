# Issues 1655 and 1656 Homogeneous Decode Coordinator

Date: 2026-05-29

## Context

Issue #1642 tracks the remaining release Gemma E4B serving gap against OMLX
and SwiftLM. The latest three-way report shows that the remaining threshold
failures are concentrated in concurrency-2 decode scenarios. The control-plane
same-cohort probe now separates scheduler admission from worker execution and
currently reports a scheduler admission cohort size of two while the Swift text
worker/model decode path remains singleton.

Issue #1655 is the first implementation slice for closing that worker-side
gap. It should add the narrow coordinator and backend contract needed to group
eligible homogeneous decode requests without claiming fused model execution for
backends that cannot actually provide it.

Issue #1656 is the hardening slice for the same path. It keeps incompatible
requests on the single-request path and proves that cancellation, stream order,
and usage accounting keep the existing decode RPC contract while one request in
a batch can finish independently from its peer.

## Plan

1. Add a Swift text decode cohort contract.
   - Represent each candidate request with its model handle, sampling,
     acceleration policy, output limit, decode step size, prefill token, cache
     snapshot requirement, and prepared prefill state.
   - Build an eligibility key from those fields so only same-model,
     same-sampling, same-acceleration, same-output-limit requests can batch.
   - Exclude requests that need boundary snapshot creation in this first slice,
     because snapshot persistence is per-request state that requires separate
     hardening.
   - Propagate the control-plane admission cohort capacity and request position
     through worker execution metadata so worker-local decode coordination can
     distinguish an actual scheduler cohort from a single request that merely
     has batching enabled.
   - Add a short control-plane admission formation window before the first
     batchable request is released. The window is only used for non-empty
     compatible cohorts with capacity greater than one, and it lets concurrent
     HTTP requests receive the same final admission cohort size instead of
     letting the first request start worker prefill as a singleton.
   - During formation, admit only the compatible front prefix that still fits
     the minimum capacity declared by its members. A later request with a
     narrower capacity must not be pulled into an earlier wider formation batch.
2. Add a worker-local decode coordinator.
   - Hold a short pending window for decode RPCs that enter with the same
     eligibility key.
   - Use the default short window for ordinary requests and the configured
     cohort pending window only when scheduler admission metadata reports an
     actual admission cohort size greater than one. A single request with
     capacity greater than one must not pay the long cohort wait.
   - Set the default scheduler-cohort decode window high enough to cover one
     serialized prefill skew for the Gemma E4B 1024-token benchmark path while
     keeping singleton decode on the short window.
   - Dispatch a cohort only when the backend advertises homogeneous batch
     decode support and the cohort size is greater than one.
   - Fall back to the existing single-request decode path otherwise.
3. Add a backend batch decode event surface.
   - Emit per-request token and summary events from one batch stream.
   - Record worker decode batch size, model eval batch size, per-batch token
     count, and per-batch token rate from the actual batch execution.
   - Record batch decode phase timings for model calls, explicit model eval
     synchronization, sampling, token-id synchronization, detokenization, and
     stream yields so release benchmark artifacts can explain remaining
     end-to-end latency gaps.
   - Enable the real Swift MLX batch path only for text-only baseline decode
     cohorts that share the same loaded `ModelContainer`, sampling policy,
     output limits, prepared prompt length, and compatible KV-cache shape.
   - Fall back inside the batch event surface for unsupported cohorts so the
     coordinator can advertise backend capability without emitting synthetic
     batch-size-two evidence for unsafe paths.
4. Prove the behavior with deterministic worker tests.
   - Two homogeneous requests should observe worker/model batch size two.
   - Two live Swift MLX homogeneous CPU-model requests should observe
     worker/model batch size two through the real backend batch surface.
   - Existing singleton decode tests should continue to report batch size one.
   - The deterministic integration evidence should avoid treating scheduler
     admission as model-step execution.
5. Harden batch decode lifecycle semantics.
   - If backend eligibility rejects a cohort, use the existing per-request
     decode path and keep batch metrics at size one.
   - If one request aborts after the batch has started, complete that request
     with the existing cancelled decode contract, omit its usage trailer, and
     continue the peer request to normal usage and completion.
   - Preserve per-request event ordering as `decodeStarted`, token deltas,
     optional usage, and `completed`.

## Success Metrics

- Homogeneous deterministic decode requests produce
  `swift_text.decode_batch_size == 2` and
  `swift_text.model_eval_batch_size == 2`.
- Control-plane phase-aware decode requests carry
  `melix.scheduler.admission_batch_capacity`,
  `melix.scheduler.admission_cohort_size`, and
  `melix.scheduler.admission_batch_position` so worker-side timing can be
  correlated with scheduler admission evidence.
- Concurrent same-cohort requests receive the same final admission cohort size
  before worker prefill starts.
- Homogeneous live Swift MLX decode requests produce per-request summaries with
  `decodeBatchSize == 2`, `modelEvalBatchSize == 2`, and a batch summary with
  the combined per-batch output token count.
- Homogeneous batch decode metrics include phase-level timing counters under
  `swift_text.decode_batch_*_us` so benchmark reports can distinguish model
  execution cost from sampling, token synchronization, detokenization, and
  stream-yield overhead. The explicit model-eval sync metrics also record
  first-step and max-step timings when the diagnostic force-eval probe is
  enabled, so diagnostics can separate one-time batch cache expansion from
  steady-state decode execution without keeping a full-logits synchronization
  in the default hot path.
- Three-way serving comparison bundles can include a `run-evidence.json`
  artifact when the operator provides build/runtime evidence. The copied
  artifact is referenced from the manifest, JSON summary, and Markdown report
  so #1642 release acceptance evidence does not depend on a sidecar file outside
  the staging bundle.
- Batch hardening tests prove unsupported homogeneous batch decode falls back to
  the single-request path, and one cancelled request in a deterministic batch
  does not prevent its peer from producing token events, a usage trailer, and a
  normal completion event.
- Singleton fallback continues to produce batch size one.
- Backend metrics are only recorded from the execution path actually used by
  the worker; unsupported Swift MLX cohorts remain singleton evidence instead
  of synthetic batch-size-two evidence.

## Diagnostic Notes

2026-06-01 local release diagnostics against
`unsloth/gemma-4-E4B-it-MLX-8bit` used the exact local snapshot
`0b58ae760a389dcdda6d4e74eab1a41bede541d1` through the Swift worker
`melix-dev-text` catalog alias. These diagnostics are not #1642 acceptance
evidence because the host had unrelated Python test and LoRA processes plus
high swap pressure, and one run used a same-stack dummy endpoint only to satisfy
the three-way script's endpoint-count validation.

The useful finding is phase attribution from a temporary forced `eval(logits)`
diagnostic. The 1024/c2 diagnostic captured real batch decode with
`swift_text.decode_batch_size_max == 2` and
`swift_text.model_eval_batch_size_max == 2`. The worker reported 63 batched
model eval sync calls, `7_219_576us` total sync time, `114_596us` average,
`85_121us` first step, and `1_903_102us` max step. That rules out a purely
first-step batch-cache expansion explanation and keeps the remaining bottleneck
in the Swift MLX Gemma 4 decode execution path under load. The production path
does not force this full-logits synchronization by default.

After removing the default forced full-logits synchronization, a single-endpoint
diagnostic still showed hot-path token-id synchronization cost:
`swift_text.decode_batch_token_id_total_us == 6_428_368` across 128 per-request
token-id synchronizations. The batch path now uses one batched argmax/token-id
sync for homogeneous greedy decode cohorts that have no logit processor. The
follow-up single-endpoint diagnostic reduced token-id synchronization to 65
calls and `4_285_475us`, while preserving real batch evidence
(`decode_batch_size_max == 2`, `model_eval_batch_size_max == 2`) and keeping
`decode_batch_model_eval_sync_call_count == 0` on the default hot path.

The 2026-06-01 three-way release run at
`.runtime/serving-comparison/gemma-e4b-20260601-latest-ae720be-rerun9/threeway/gemma-e4b-mainae720be-release-threeway-20260601-rerun9-full`
records the release binary paths, SHA-256 hashes, peer revisions, exact model
snapshot, ports, and measurement profile in `run-evidence.json`. The run used
the same prompt matrix as #1642 but passed explicit threshold arguments
`1.25/0.75`; the #1642 acceptance threshold is 25%, so the same summary rows
were recomputed into `acceptance-25pct-recompute.json` and
`acceptance-25pct-recompute.md`. That recompute is `threshold_failed`: 128/c1,
128/c2, and 1024/c1 still miss the 25% total/decode gates, while 1024/c2 passes
both gates. Therefore this slice is valid implementation and attribution
evidence for #1654/#1656, but it does not close the root #1642 performance
acceptance.
