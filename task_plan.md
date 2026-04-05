# Task Plan

## Goal

Close `M14.3` by making redo and reiteration actions operator-visible and by turning image request
timeouts into explicit, longer-running creative-workflow policy instead of generic worker
unavailable failures.

## Scope

- persist enough image job recipe state to redo or reiterate from stable control-plane truth
- expose always-visible redo and reiteration actions in the Window UI image workspace
- apply a creative image request timeout policy with a `30-minute` default and typed timeout errors
- keep timeout, retry, and cancel state distinguishable across control-plane, HTTP, and Window UI
  surfaces

## Measurement Points

- selected image jobs expose stable recipe state for prompt, size, creative parameters, and source
  lineage without relying on Window-UI-local copies
- redo can re-submit the selected job from persisted job state, and reiterate can seed an iterate
  workflow from a selected generated artifact
- image worker timeouts surface as explicit `deadline_exceeded` failures rather than collapsing into
  generic worker-unavailable errors
- the active image timeout policy remains operator-visible through snapshot or job state projection
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Current-state review and execution contract
   - status: completed
   - evidence:
     - reviewed `M14.3` and the umbrella `M14` plan plus the current image workspace and confirmed
       the Window UI still exposes only generate/edit submit and cancel actions, with no redo or
       reiterate workflow on top of the typed `variation` and `iterate` contract
     - inspected the control-plane, OpenAI image handler, Python bridge, and image read-model paths
       and confirmed image requests currently have no explicit long-running timeout policy and map
       bridge failures into generic unavailable states
2. Persisted recipe and timeout policy projection
   - status: completed
   - evidence:
     - extended the control-plane image job summary contract with `recipe`,
       `request_timeout_seconds`, and recipe-summary projection so selected jobs keep stable prompt,
       size, strength, negative prompt, and lineage truth for redo or reiteration flows
     - projected the active image timeout policy through control-plane snapshot and request summary
       truth so the Window UI can inspect the creative-workflow deadline without relying on
       desktop-local defaults
3. Timeout-aware bridge and control-plane mapping
   - status: completed
   - evidence:
     - added a default `30-minute` image request deadline in the Python bridge with deterministic
       test override coverage through `MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS`
     - mapped image worker deadline failures into typed `deadline_exceeded` image-job failures,
       explicit `timed_out` progress state, and OpenAI-compatible `504` responses instead of
       collapsing into generic unavailable failures
4. Window UI redo and reiteration flows
   - status: completed
   - evidence:
     - added always-visible redo and reiteration actions, timeout-policy inspection, timeout-aware
       status text, and edit-mode/source-artifact inspection in the Window UI image workspace and
       inspector
     - drove redo and reiteration from persisted job recipe state plus artifact lineage instead of
       UI-local temporary copies
5. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - reran focused Swift control-plane and menu-bar suites plus focused Python and integration
       timeout coverage, then measured changed-line coverage for the touched Swift and Python scope
       above the `95%` threshold
     - updated the roadmap execution index and progress log to close `M14.3`

## Acceptance

- redo flows and longer-running timeout policy are explicit, operator-visible, and test-covered
- timeout-triggered image failures remain distinguishable from cancelation and generic worker
  failures
- reiteration actions are backed by stable image-job lineage rather than ad hoc desktop-only state

## Risks

- storing too little recipe state will make redo or reiteration depend on ephemeral UI inputs
- adding timeout handling only in one surface could leave HTTP and local Window UI behavior
  inconsistent
- timeout escalation could leak bridge subprocesses if the timeout policy does not terminate the
  worker-bridge command cleanly

## Outcome

- m14_3_redo_timeout_policy_completed
