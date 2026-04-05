# Task Plan

## Goal

Close the third executable `M13.2` slice by turning speculative-decoding defaults into typed,
persistent, control-plane-validated serving-default truth and by restoring isolated integration
startup state for the gateway-defaults stack.

## Scope

- extend the gateway serving-defaults contract with speculative-decoding controls
- persist operator defaults for speculative acceleration mode, `draft_model_id`, and
  `num_draft_tokens` beside the existing generation and batching defaults
- project requested and effective speculative defaults through `ServerSnapshot`
- route text request shaping and coordinator-side acceleration resolution through gateway-owned
  speculative defaults while preserving model-level precedence
- migrate the Window UI server workspace so speculative defaults hydrate from control-plane truth
  rather than session-local draft state
- fail explicitly when speculative defaults target unsupported served models or unsupported worker
  backends

## Measurement Points

- speculative defaults must be typed, persistent, and inspectable through
  `ServerSnapshot.serving_defaults`
- request translation must carry gateway-owned speculative defaults into execution metadata without
  bypassing model-level acceleration merges
- `RequestCoordinator` must resolve effective acceleration mode, draft model id, and
  `num_draft_tokens` from gateway defaults plus model settings instead of depending on model-only
  defaults
- invalid speculative defaults must fail explicitly before persistence when the served model or
  active backend cannot support the requested speculative mode
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
2. Typed speculative defaults
   - status: completed
   - evidence:
     - extended `ApplyServingDefaults`, `ServingDefaultsSessionSummary`, and `AccelerationPolicy`
       with typed speculative-decoding fields for `acceleration_mode`, `draft_model_id`, and
       `num_draft_tokens`, then regenerated the Swift, Python, and descriptor artifacts
     - persisted speculative gateway defaults in `GatewayServingDefaultsStore`, validated them in
       `ControlPlaneService`, merged them in `RequestCoordinator`, and projected requested versus
       effective speculative state through the desktop shell
     - routed speculative defaults through `TextRequestShaper`, `ChatRequestTranslator`, and the
       shared XPC client so Window UI apply actions no longer depend on session-local draft state
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - reran `make proto`, `make py-test`, focused coverage-enabled Swift suites, and
       `make integration-test`
     - isolated integration stack persistence roots in `tests/integration/helpers.py` so
       gateway-config and serving-default overrides no longer leak from prior local runs
     - prepared roadmap, plan, and progress updates marking `M13.2` complete with explicit
       coverage and verification evidence

## Acceptance

- gateway speculative defaults are operator-visible, persistent, and backed by control-plane truth
- effective speculative state remains consistent across request translation, coordinator-side model
  merges, and desktop surfaces
- gateway defaults can request speculative decode with explicit draft-model and draft-token policy,
  and unsupported targets fail before persistence rather than surfacing as silent no-ops

## Risks

- speculative defaults could remain display-only if request translation only stores UI state and
  never feeds coordinator-visible acceleration metadata
- model-level acceleration defaults could override gateway speculative defaults incorrectly unless
  precedence is centralized in `RequestCoordinator`
- speculative defaults might accept unsupported served models unless validation checks both the
  served model route and the active Swift text backend capability before persistence

## Outcome

- m13_2_speculative_defaults_completed
