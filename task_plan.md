# Task Plan

## Goal

Close `M16.3` by making temporary media artifacts created for multimodal analysis explicit,
deterministically cleaned up, and failure-visible through worker runtime state instead of leaving
cleanup hidden inside ad hoc temporary-directory scopes.

## Scope

- introduce one repository-owned temporary-media lifecycle helper for VLM analysis assets
- replace implicit `TemporaryDirectory` cleanup in the MLX VLM runtime with explicit artifact
  registration, cleanup reporting, and deterministic failure handling
- project temporary-media cleanup evidence into worker runtime stats and control-plane metrics
- add focused worker, control-plane, and integration coverage for success, cancellation, and
  cleanup-failure branches
- update the active M16.3 plan and roadmap bookkeeping once acceptance is met

## Measurement Points

- temporary analysis assets are created under one inspectable session root with explicit artifact
  counts and byte totals
- success, failure, and cancellation paths all execute the same cleanup policy rather than relying
  on hidden context-manager teardown
- worker runtime stats surface cleanup artifact count, cleanup latency, and cleanup failure count
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. Current-state review and M16.3 boundary lock
   - status: completed
   - evidence:
     - reviewed the parent `M16` roadmap slice plus the dedicated `M16.3` plan
     - confirmed the current executable temp-media path is concentrated in
       `worker/runtime/mlx_vlm_runtime.py`, with cleanup still implicit through
       `TemporaryDirectory`
     - confirmed `M16.3` should stop at worker lifecycle, cleanup observability, and runbook
       evidence rather than expanding into benchmark or operator-shell work (`M16.4`)
2. Temporary-media lifecycle helper and runtime adoption
   - status: completed
   - evidence:
     - added `worker/runtime/temp_media_lifecycle.py` so one repository-owned temp-media session
       now records staged artifact count, byte totals, cleanup latency, and cleanup failures
     - adopted that helper in both deterministic and MLX VLM runtimes, replacing hidden temporary
       directory teardown with explicit success, failure, and cancellation cleanup
     - updated prepared video inputs to preserve inline bytes so staged multimodal analysis assets
       share one deterministic lifecycle surface
3. Runtime stats, control-plane metrics, and failure projection
   - status: completed
   - evidence:
     - extended worker runtime stats plus registry bookkeeping with
       `last_temp_media_artifact_count`, `last_temp_media_artifact_bytes`,
       `last_temp_media_cleanup_latency_ms`, and `last_temp_media_cleanup_failure_count`
     - projected temporary-media cleanup evidence through control-plane OCR and VLM metric
       publication so multimodal routes expose cleanup visibility outside Python logs
4. Focused verification and roadmap bookkeeping
   - status: completed
   - evidence:
     - added focused Python, Swift, and integration tests that cover success, cancellation, and
       cleanup-failure branches across runtime, registry, control-plane, and lifecycle integration
     - focused Python changed-line coverage reached `95.83%` (`207/216`) and focused Swift
       changed-line coverage reached `100.00%` (`64/64`)
     - `progress.md`, the dedicated `M16.3` plan, and the roadmap execution index are updated
       together with the implementation once the full verification summary is recorded

## Acceptance

- temporary media artifacts are created and cleaned through one explicit lifecycle helper
- cleanup failures are surfaced through stable runtime-state counters and test-covered metrics
- success, failure, and cancellation all prove deterministic cleanup behavior
- focused verification already proves the touched scope at or above `95%` changed-line coverage
  before commit, with full-repository verification being recorded in `progress.md`

## Risks

- if cleanup remains hidden inside `TemporaryDirectory`, future video frame extraction and transcode
  work will be impossible to observe or recover cleanly
- if cleanup counters live only in Python logs, the control plane will not be able to distinguish
  worker-health regressions from benign request failures
- if `M16.3` starts inventing operator-shell UI now, it will blur the boundary with `M16.4`
