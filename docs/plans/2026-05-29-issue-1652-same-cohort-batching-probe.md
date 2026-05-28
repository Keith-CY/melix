# Issue 1652 Same-Cohort Batching Probe

Date: 2026-05-29

## Context

Issue #1642 tracks the remaining release Gemma E4B serving gap against OMLX and SwiftLM. The next dependency slice is #1652: prove whether same-cohort requests are only admitted together by the control plane or actually decoded together at the worker/model step.

The architecture spec currently limits the continuous-batching baseline to Swift text phase-aware prefill work. Existing scheduler metrics expose admission-level state such as `scheduler.continuous_batch_size`, but they must not be treated as proof that the worker executes a fused model-step batch.

## Plan

1. Add a deterministic two-request same-cohort probe seam around `RequestCoordinator`.
   - Use the existing phase-aware worker test seam so the probe does not require OMLX, SwiftLM, or a real model.
   - Keep request IDs stable so gateway/coordinator/worker/decode observations can be linked.
2. Persist a machine-readable probe contract.
   - Record scheduler admission metrics, request progress snapshots, prefill/decode request IDs, decode handles, model-step batch size evidence, decode loop iterations, and aggregate output throughput.
   - Warn when admission batch size is greater than 1 while worker/model-step batch size remains 1.
3. Add a runnable script wrapper.
   - Run the focused Swift probe test, extract its JSON evidence, analyze it, and optionally write the combined payload to disk.
   - Support an input-only mode for fast unit tests and later artifact re-analysis.
4. Verify with focused Swift and Python tests.
5. Register the probe with PR-scoped performance so changes to the script, Swift
   probe seam, tests, or governing plan select the macOS runner probe in CI.
   The registered `command_json` probe emits flat numeric metrics for scheduler
   admission batch size, worker/model-step batch size, warning/failure counts,
   linked request count, and the scheduler-to-worker batch delta.

## Success Metrics

- The probe reports `warning` for the current implementation if `scheduler.continuous_batch_size > 1` and `worker.max_model_step_batch_size == 1`.
- The JSON evidence links both request IDs across gateway/coordinator worker prefill/decode request IDs.
- The probe completes without peer runtimes and without a real model.
