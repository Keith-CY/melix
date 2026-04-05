# Task Plan

## Goal

Close the first executable `M13.4` slice by projecting supported API surfaces and endpoint
reference through one typed, control-plane-owned onboarding summary that the desktop API workspace
can render without stale hardcoded catalogs.

## Scope

- add a typed `api_onboarding` snapshot summary under `ServerSnapshot`
- project supported API surfaces and live endpoint reference from control-plane truth
- replace the static desktop API endpoint catalog with the typed snapshot summary
- generate session-aware quick-start snippets in the desktop API workspace from the typed summary
  plus selected server-session auth and base-URL state
- keep Ollama guidance truthful by projecting an explicit compatibility boundary instead of
  pretending native `/api/*` routes already ship

## Measurement Points

- `ServerSnapshot.api_onboarding` must remain populated after handshake and snapshot refresh
- endpoint reference must reflect the shipped gateway routes instead of a desktop-local static list
- quick-start snippets must use selected server-session auth, base URL, and model truth
- OpenAI, Anthropic, and Ollama onboarding rows must stay explicit about what is shipped versus
  compatibility-only guidance
- changed-line coverage for the touched handwritten executable scope must remain at or above `95%`

## Phases

1. Planning and snapshot contract
   - status: completed
   - evidence:
     - identified the current gap: the desktop API workspace still renders a stale phase-4 static
       endpoint catalog and uses external-agent exports instead of product-owned API quick starts
     - selected a bounded first slice: add a typed `api_onboarding` snapshot summary and rehydrate
       the existing API workspace from that summary before considering broader compatibility work
2. Typed API onboarding summary and desktop hydration
   - status: completed
   - evidence:
     - extended `ServerSnapshot` with a typed `api_onboarding` summary covering published API
       surfaces, per-endpoint reference rows, surface status, and compatibility notes
     - added `APIOnboardingSnapshotSource` so the Swift control plane now owns the shipped API
       onboarding catalog instead of the desktop shell reconstructing it from static constants
     - replaced the desktop API reference catalog with snapshot-driven `apiSurfaces` and
       `apiReference` rows, preserving surface grouping and compatibility-only guidance
     - generated session-aware OpenAI, Anthropic, and Ollama quick-start snippets from the
       selected server session's effective base URL, auth state, and served model
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - focused control-plane and menu-bar suites passed with code coverage enabled
     - touched-scope aggregate changed-line coverage reached `96.67% (784/811)`
     - `make swift-test` still fails outside this slice in `services/mlx-text-worker-swift`
       because `WorkerScaffoldTests` exits with signal `11`

## Acceptance

- the desktop API workspace renders endpoint reference from typed control-plane truth
- quick-start snippets are session-aware and match the shipped local API surface
- operators can inspect OpenAI, Anthropic, and Ollama onboarding guidance without guessing which
  routes are actually supported

## Risks

- the desktop API workspace could remain stale if endpoint reference keeps living in a static UI
  catalog instead of a typed snapshot summary
- quick-start snippets could drift from live auth and model truth if they are copied from docs
  instead of generated from the selected session
- Ollama onboarding could become misleading if the product implies native `/api/*` support before
  those routes exist

## Outcome

- m13_4_api_onboarding_slice_1_completed
