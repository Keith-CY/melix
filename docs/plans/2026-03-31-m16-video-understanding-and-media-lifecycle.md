# M16 Video Understanding And Media Lifecycle

## Status

Completed on 2026-04-06. `M16.1-M16.4` now collectively provide explicit video ingress contracts,
frame-policy and background-lane routing, temporary-media lifecycle control, and repository-owned
video operator evidence plus runbook guidance.

## Goal

Add first-class video-understanding support to Melix, with explicit media normalization, frame-selection policy, background-lane scheduling, and temporary-media lifecycle control instead of treating video as an unbounded extension of image requests.

## Scope

- add video request normalization and validation
- define frame-selection and multi-frame analysis policy
- route video analysis through explicit background-lane and cache-aware paths
- manage temporary media artifacts and cleanup deterministically
- publish video-focused benchmarks, runbooks, and operator evidence

## Coverage

- local-path, local-file-URI, remote-URL, and inline video ingress through one normalized media path
- frame-sampling, frame-budget, and duration-bound policy for video analysis requests
- multi-frame request semantics compatible with vision-language runtime contracts
- background-lane routing for video workloads so they do not silently degrade interactive text traffic
- temporary media-file cleanup for extracted frames, transcodes, and intermediate analysis assets
- video-focused metrics for preprocessing latency, frame extraction cost, first-token latency, queue delay, and cleanup failures

## Execution Slices

- `M16.1` Video ingress and media-normalization contracts
- `M16.2` Frame policy, video runtime shaping, and background-lane routing
- `M16.3` Temporary-media lifecycle, cleanup, and failure recovery
- `M16.4` Video integration benchmarks, runbooks, and operator evidence

## Files

- update `packages/protocol/schema/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/EnginePool/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- Video support should remain analysis-first and should not inherit image-only assumptions about payload size or preprocessing cost.
- Frame selection must be explicit and inspectable so operator-visible behavior matches runtime cost.
- Cleanup paths must run for both success and failure cases to avoid leaving temporary media artifacts behind.
- Video scheduling should compose with existing multimodal isolation rules rather than creating a second ungoverned background lane.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`
- video-runtime smoke command for the touched scope

## Acceptance

- Video requests are normalized, bounded, and routed through explicit Melix request semantics.
- Video analysis does not bypass scheduling, cache, or cleanup policy.
- Temporary media artifacts are cleaned up deterministically and operator-visible failure states are test-covered.
- Video benchmarks and runbooks record concrete preprocessing, routing, and latency evidence.
