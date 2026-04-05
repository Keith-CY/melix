# Task Plan

## Goal

Advance `M13.2` by turning gateway-level generation defaults into typed control-plane truth before
expanding into batching and speculative-decoding settings.

## Scope

- define the first executable `M13.2` slice around gateway-owned generation defaults and stream
  interval state
- persist operator defaults for `temperature`, `top_p`, `max_tokens`, and `stream_interval_tokens`
- project requested and effective defaults through `ServerSnapshot`
- route text request shaping through gateway defaults before request-level overrides while
  preserving model-level generation config precedence
- migrate the Window UI advanced serving-default controls off desktop-only session state

## Measurement Points

- gateway-level generation defaults must be typed, persistent, and inspectable through
  `ServerSnapshot`
- request translation must merge gateway defaults, model-level generation config, and explicit
  request overrides deterministically
- Window UI server defaults must hydrate from control-plane truth rather than transient local
  draft state
- changed-line coverage for the touched Swift scope must remain at or above `95%`

## Phases

1. Planning and contract refinement
   - status: completed
   - evidence:
     - refined `M13.2` into three executable slices: generation defaults, batching or admission
       defaults, and speculative defaults
     - selected the generation-defaults slice as the next implementation target because it closes
       an existing divergence between desktop-only state and request-shaping truth
2. Gateway generation-defaults state model
   - status: in_progress
   - evidence:
     - next work adds a typed serving-defaults command, persistence flow, snapshot projection, and
       request-merge path for `temperature`, `top_p`, `max_tokens`, and `stream_interval_tokens`
3. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - add focused control-plane, HTTP gateway, and menu-bar coverage for typed defaults and
       effective request shaping
     - record coverage and metrics before closing the first executable `M13.2` slice

## Acceptance

- gateway generation defaults are operator-visible, persistent, and backed by control-plane truth
- effective defaults remain consistent across request translation and desktop surfaces
- model-level generation config still overrides gateway defaults, and explicit request fields still
  override both

## Risks

- generation defaults could drift between desktop state and request shaping if they are projected
  in snapshots but not consumed by the translator
- precedence could become ambiguous if model-level generation config and gateway defaults are not
  merged in one place
- batching and speculative defaults could bleed into this slice if the serving-defaults state model
  is not narrowly scoped

## Outcome

- m13_2_generation_defaults_planned
