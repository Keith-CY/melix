# Task Plan

## Goal

Close `M11.3` by exposing streaming-compatible cache policy and settings surfaces so disk-streamed
execution has explicit, operator-visible cache compatibility rules instead of hidden downgrade
paths.

## Scope

- define the authoritative cache-compatibility contract that applies when disk streaming or other
  large-model safety policies are active
- surface cache-memory limits, cache directories, cache block policy, and multimodal cache budgets
  through control-plane truth and native operator settings
- make effective cache-policy resolution observable after merges, overrides, and safety-driven
  downgrades

## Measurement Points

- streaming-compatible cache settings must expose both requested policy and effective resolved
  policy after control-plane merges or safety downgrades
- operator surfaces must explain when cache tiers are disabled, bounded, or redirected because of
  disk-streaming compatibility or memory-aware policy
- repository-owned verification must demonstrate that cache compatibility rules stay aligned across
  control-plane truth, worker-facing settings, and native desktop presentation

## Phases

1. Cache-policy contract audit and gap definition
   - status: in_progress
   - evidence:
     - compare the current cache-tier settings, disk-streaming mode, and large-model safety policy
       against the `M11.3` milestone contract and identify what remains hidden, downgraded, or
       untyped
     - define the exact compatibility settings, measurement points, and effective-policy payloads
       before broad implementation
2. Control-plane, runtime, and operator propagation
   - status: pending
   - evidence:
     - thread streaming-compatible cache settings through control-plane orchestration, worker-facing
       requests, and model or session state
     - ensure effective cache policy, bounded budgets, and compatibility downgrades surface
       explicit typed state and metrics instead of hidden fallback behavior
3. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - run the authoritative verification commands for the touched scope, including integration
       coverage if the live path changes or cache compatibility affects live serving paths
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M11.3`
       completed only after control-plane, worker, operator, and verification evidence is captured

## Acceptance

- streaming-compatible cache policy and settings are explicit, operator-visible, and test-covered
- effective cache settings can be inspected after merges, overrides, and safety-driven downgrades
- control-plane truth and worker execution remain aligned on cache compatibility and memory-aware
  policy

## Risks

- leaving cache compatibility rules implicit would make streamed-model performance and warm-path
  behavior difficult to diagnose when cache tiers are silently disabled or downgraded
- exposing requested cache settings without the effective resolved policy would confuse operators
  when disk-streaming safety policy overrides the request
- duplicating compatibility rules in multiple layers would invite drift between control-plane
  orchestration truth, worker execution truth, and native desktop presentation

## Outcome

- m11_3_streaming_cache_compatibility_and_settings_surface_in_progress
