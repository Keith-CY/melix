# Issue 1655 Homogeneous Decode Coordinator

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
2. Add a worker-local decode coordinator.
   - Hold a short pending window for decode RPCs that enter with the same
     eligibility key.
   - Dispatch a cohort only when the backend advertises homogeneous batch
     decode support and the cohort size is greater than one.
   - Fall back to the existing single-request decode path otherwise.
3. Add a backend batch decode event surface.
   - Emit per-request token and summary events from one batch stream.
   - Record worker decode batch size, model eval batch size, per-batch token
     count, and per-batch token rate from the actual batch execution.
   - Keep unsupported Swift MLX paths on the singleton event surface until a
     real shared-cache MLX batch implementation lands.
4. Prove the behavior with deterministic worker tests.
   - Two homogeneous requests should observe worker/model batch size two.
   - Existing singleton decode tests should continue to report batch size one.
   - The deterministic integration evidence should avoid treating scheduler
     admission as model-step execution.

## Success Metrics

- Homogeneous deterministic decode requests produce
  `swift_text.decode_batch_size == 2` and
  `swift_text.model_eval_batch_size == 2`.
- Singleton fallback continues to produce batch size one.
- Backend metrics are only recorded from the execution path actually used by
  the worker; unsupported real Swift MLX batch decode does not emit synthetic
  batch-size-two evidence.
