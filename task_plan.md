# Task Plan

## Goal

Close the first executable `M13.2` slice by turning gateway-level generation defaults into typed
control-plane truth before the next batching and speculative-decoding slices.

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
   - status: completed
   - evidence:
     - added a typed `server.apply_serving_defaults` command plus protobuf summaries for requested
       and effective serving defaults, and regenerated the versioned Swift, Python, and
       descriptor artifacts
     - persisted operator serving defaults through `GatewayServingDefaultsStore`, projected them
       through `ServerSnapshot`, and wired gateway defaults into request shaping before request
       overrides while preserving model-level generation-config precedence
     - updated the Window UI server workspace so serving-default values, source metadata, and
       effective merged defaults hydrate from control-plane truth and server starts persist the
       typed defaults before lifecycle mutation
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - focused control-plane, HTTP gateway, and menu-bar coverage now exercises typed defaults,
       effective request shaping, server-start persistence, and UI projection
     - changed-line coverage for the touched handwritten Swift scope closed at or above the
       repository `95%` gate before commit

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

- m13_2_generation_defaults_completed
