# Task Plan

## Goal

Close `M16.4` by leaving video understanding with one repository-owned operator-evidence workflow:
live-path smoke coverage for representative video requests, measurable preprocessing/routing/latency
data, and a runbook that explains how to reproduce and diagnose the current video path.

## Scope

- add a repository-owned `M16.4` video smoke command or script that exercises:
  - one short local video path
  - one remote video URL
  - one bounded multi-frame workload
- capture operator-relevant metrics for video requests, including preprocessing, routing, latency,
  frame-policy, and cleanup evidence
- add integration and unit coverage for the smoke payload and any new metrics-report helper
- document the workflow in a dedicated runbook and update repository indexes once complete

## Measurement Points

- smoke output records per-scenario request latency and control-plane metric evidence
- at least one scenario proves local-path video ingress, one proves remote-URL ingress, and one
  proves bounded multi-frame window semantics
- operator evidence includes background-lane or queue diagnosis signals rather than only response
  payload checks
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. M16.4 boundary lock and evidence-shape design
   - status: completed
   - evidence:
     - reviewed the umbrella `M16` roadmap slice, the dedicated `M16.4` plan, and existing smoke
       patterns used by `M9.3`, `M11.4`, `M15.4`, and Phase 6 multimodal metrics reporting
     - confirmed the preferred shape is a repository-owned smoke script plus metrics-report helper,
       with no new operator UI surface required in this slice
2. Video smoke workflow and metrics report implementation
   - status: completed
   - evidence:
     - added `scripts/m16_video_runtime_smoke.py` so one repository-owned smoke workflow now
       exercises local-path, remote-URL, bounded inline multi-frame, and routing-under-load video
       requests through the live HTTP path
     - added `build_phase16_video_metrics_report(...)` plus export wiring so the touched scope now
       emits machine-readable success rates and operator metrics for video request latency,
       frame-policy, cleanup, and scheduler evidence
3. Integration coverage and runbook evidence
   - status: completed
   - evidence:
     - added `tests/integration/test_video_runtime_smoke.py` and expanded
       `services/mlx-worker-python/tests/test_acceptance_metrics.py` so the smoke payload and
       acceptance-metrics helper are covered together
     - added `docs/runbooks/video-understanding-evidence.md` plus runbook and docs indexes so
       reproduction, metric interpretation, cleanup diagnosis, and background-lane debugging are
       documented in one repository-owned path
4. Verification and roadmap bookkeeping
   - status: completed
   - evidence:
     - focused `pytest` verification passed for the touched Python and integration scope, Python
       changed-line coverage reached `100.00%` (`52/52`), and full `make py-test` passed
     - `progress.md`, the dedicated `M16.4` plan, the umbrella `M16` roadmap file, and the
       execution index are updated together once acceptance is met

## Acceptance

- the repository owns reproducible live-path operator evidence for representative video workloads
- smoke output records truthful preprocessing, routing, latency, frame-policy, and cleanup data
- runbook guidance explains how to reproduce and diagnose the current video path without unwritten
  context
- verification proves the touched executable scope at or above `95%` changed-line coverage before
  commit, and the current touched Python scope reaches `100.00%` (`52/52`)

## Risks

- if the smoke workflow only checks response text, `M16.4` will miss the operator-evidence goal
- if remote-URL video evidence depends on an external network resource, the smoke will become
  flaky and non-repository-owned
- if the runbook omits queue and cleanup diagnosis, contributors will still need code spelunking to
  interpret video failures
