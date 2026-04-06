# Task Plan

## Goal

Close `M15.1` by adding UI-side chat token presentation smoothing in the desktop shell while
preserving exact streamed content fidelity, event ordering, and measurable runtime-to-UI lag.

## Scope

- add menubar-owned chat presentation buffering for streamed assistant, reasoning, and tool deltas
- keep the underlying control-plane stream contract unchanged and preserve transcript fidelity
- expose measurable presentation-lag evidence so regressions remain visible after smoothing
- add focused menu-bar test coverage for partial presentation, final transcript fidelity, and lag
  metrics
- update milestone bookkeeping once the slice is verified and committed

## Measurement Points

- bursty chat deltas are presented in multiple UI flushes instead of one immediate transcript jump
- the final assistant, reasoning, and tool transcript bodies still match the exact streamed content
- a dedicated presentation-lag metric records the added UI-side delay instead of hiding it
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Current-state review and smoothing boundary definition
   - status: completed
   - evidence:
     - reviewed `M15.1`, the `M15` umbrella plan, and the current `RuntimeViewModel` streaming
       path and confirmed that assistant, reasoning, and tool deltas append directly to transcript
       rows with no UI-side presentation layer
     - confirmed the milestone scope can stay inside the macOS menu-bar package because the plan
       only requires desktop-shell smoothing and measurable lag, not protocol or worker changes
2. Menubar-side smoothing implementation
   - status: completed
   - evidence:
     - added a menubar-owned presentation queue plus flush cadence in `RuntimeViewModel` for
       assistant, reasoning, and tool deltas while preserving exact global text order
     - ensured completion, failure, transport-error, and transcript-clear paths flush or reset
       buffered text deterministically so terminal transcript state stays faithful
3. Focused menu-bar coverage and lag assertions
   - status: completed
   - evidence:
     - extended `RuntimeViewModelTests` and `FakeControlPlaneXPCClient` so scheduled bursty chat
       streams can prove partial presentation, final fidelity, and lag-metric recording
     - kept existing transcript-merging and reasoning/tool coverage passing so the new smoothing
       layer stays transparent to final transcript truth
4. Verification, metrics, and milestone bookkeeping
   - status: completed
   - evidence:
     - ran coverage-enabled focused menu-bar verification, changed-line coverage reporting, and the
       repository `make swift-test` command
     - captured the existing out-of-scope `services/mlx-text-worker-swift` `signal 11` failure
       boundary while the touched menu-bar package passed

## Acceptance

- token presentation is visibly smoother without changing content fidelity or transcript ordering
- runtime-to-UI presentation lag remains measurable after smoothing is enabled
- the touched menu-bar scope is test-covered well enough to keep changed-line coverage at or above
  `95%`

## Risks

- if non-text terminal events do not flush pending buffered text, final transcripts can truncate or
  mis-order streamed content
- if smoothing buffers only one transcript lane, reasoning or tool rows can jump ahead of earlier
  assistant output and violate ordering guarantees
- if lag metrics are not recorded separately, the UI can appear smoother while hiding transport or
  presentation regressions

## Outcome

- m15_1_token_stream_presentation_smoothing_completed
