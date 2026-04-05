# Task Plan

## Goal

Close the second executable `M13.2` slice by turning batching and admission defaults into typed,
persistent, and request-coordinator-visible control-plane truth.

## Scope

- extend the gateway serving-defaults contract with concurrent-processing and batching controls
- persist operator defaults for `concurrent_processing_enabled`, `prefill_batch_size`, and
  `completion_batch_size` beside the existing generation defaults
- project requested and effective batching or admission defaults through `ServerSnapshot`
- route text request shaping and scheduler admission through gateway-owned batching defaults
- migrate the Window UI server workspace so batching or admission controls hydrate from
  control-plane truth rather than session-local draft state

## Measurement Points

- batching and admission defaults must be typed, persistent, and inspectable through
  `ServerSnapshot.serving_defaults`
- request translation must carry gateway-owned batching defaults into scheduler-visible execution
  metadata
- `RequestCoordinator` must derive effective continuous-batch capacity from gateway defaults rather
  than the current hard-coded target size
- changed-line coverage for the touched Swift scope must remain at or above `95%`

## Phases

1. Planning and contract refinement
   - status: completed
   - evidence:
     - confirmed `M13.2` Slice 2 should use the existing serving-defaults truth path instead of
       inventing a second gateway settings surface
     - identified the handwritten drift: `GatewayServingDefaultsStore` and the Window UI only
       expose generation defaults, while `RequestCoordinator` still hard-codes
       `continuousBatchTargetSize = 2` and does not consume gateway admission metadata
     - selected the executable slice around `concurrent_processing_enabled`,
       `max_concurrent_requests` as the operator-visible max concurrent sequence cap, plus
       `prefill_batch_size` and `completion_batch_size`
2. Typed batching or admission defaults
   - status: completed
   - evidence:
     - extended `ApplyServingDefaults` and `ServingDefaultsSessionSummary` so
       `concurrent_processing_enabled`, `prefill_batch_size`, and `completion_batch_size` are
       versioned protocol fields rather than Window-UI-only drafts
     - persisted batching defaults inside `GatewayServingDefaultsStore`, projected requested and
       effective batching state through `ServerSnapshot`, and routed those values into request
       shaping plus scheduler-visible execution metadata
     - removed the `RequestCoordinator` hard-coded continuous-batch target and replaced it with a
       gateway-default-driven effective admission batch size that can expand, shrink, or disable
       continuous batching
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - `make proto` passed and `git diff --check` is clean
     - focused control-plane and Window UI Swift suites passed for the touched scope
     - changed-line coverage stayed above the repository gate with `95.41%` for the touched
       control-plane scope, `99.59%` for the touched menu-bar scope, and `96.81%` aggregated
     - `make swift-test` still fails outside the touched scope at
       `services/mlx-text-worker-swift` with an unexpected signal `11`, so that package remains a
       repository-level follow-up rather than a regression introduced by this slice

## Acceptance

- gateway batching and admission defaults are operator-visible, persistent, and backed by
  control-plane truth
- effective defaults remain consistent across request translation, scheduler admission, and desktop
  surfaces
- gateway defaults can disable continuous batching or shrink batch capacity without editing source

## Risks

- batching defaults could remain display-only if request translation does not pass them into
  scheduler-visible execution metadata
- `RequestCoordinator` could keep using a hard-coded batch size if default resolution is not
  centralized
- the existing `maxConcurrentRequests` field could become semantically ambiguous unless it is
  explicitly treated as the operator-visible max concurrent sequence cap for this slice

## Outcome

- m13_2_batching_defaults_completed
