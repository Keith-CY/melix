# Task Plan

## Goal

Close `M15.4` by adding repository-owned desktop-polish integration evidence that proves token
presentation smoothing, unified banner and download-recovery behavior, and product-shell navigation
grounding through a reproducible smoke command, integration coverage, and operator runbook.

## Scope

- add a focused Swift smoke suite that exercises bursty chat presentation, shared desktop signals,
  download recovery, operator-session restore, and surface or tool-section navigation in one flow
- wrap the Swift smoke in a repository-owned script so contributors can run it without rediscovering
  the package command or output contract
- add Python-side script coverage and an integration test that executes the smoke and validates its
  machine-readable payload
- document the smoke workflow, expected metrics, and recovery interpretation in a dedicated runbook

## Measurement Points

- the smoke emits canonical metrics for chat-presentation lag, queue recovery visibility, update
  signal visibility, persisted queue restore, and surface or tool-section grounding counts
- the smoke covers all `DesktopSurface` cases and all `DesktopToolSection` cases without falling
  back to non-rendering placeholders
- the integration test executes the repository-owned smoke command and validates the published
  payload instead of reimplementing its logic
- changed-line coverage for the touched executable scope remains at or above `95%`

## Phases

1. Current-state review and smoke-contract definition
   - status: completed
   - evidence:
     - reviewed `M15.4`, the `M10-M15` executable goals, current menu-bar smoke patterns, the
       desktop workspace shell, and the existing runbooks for admin persistence and desktop chat
     - selected a repository-owned smoke design that reuses `FakeControlPlaneXPCClient`,
       `RuntimeViewModel`, and SwiftUI host rendering instead of introducing a second desktop
       harness
2. Swift smoke implementation and navigation grounding
   - status: completed
   - evidence:
     - added `DesktopPolishSmokeTests` so one focused suite now exercises bursty chat presentation,
       registry-backed download recovery, update-signal priority, operator-session restore, and
       public destination-view grounding across all `5` desktop surfaces plus all `6` tool sections
     - stabilized the smoke harness around public SwiftUI destination views instead of brittle
       shell-text scraping, then emitted the canonical `M15_DESKTOP_POLISH_SMOKE=<json>` payload
     - focused Swift verification now passes under both the plain and coverage-enabled menu-bar
       test commands
3. Script, Python coverage, and integration execution
   - status: completed
   - evidence:
     - added `scripts/m15_desktop_polish_smoke.py` so contributors can run the smoke through one
       repository-owned JSON contract with repo-local SwiftPM environment defaults
     - added `tests/test_m15_desktop_polish_smoke.py` and
       `tests/integration/test_desktop_polish_smoke.py` so both the script projection and the
       end-to-end smoke command stay covered
     - Python changed-line coverage for the touched script plus tests is now `99.06%` (`105/106`)
4. Runbook, metrics report, coverage, and milestone bookkeeping
   - status: completed
   - evidence:
     - added `docs/runbooks/desktop-polish.md` and indexed it from the runbook maps so operators
       can reproduce the smoke command and interpret the payload without rediscovering context
     - Swift changed-line coverage for `DesktopPolishSmokeTests.swift` is `98.69%` (`301/305`)
     - Python changed-line coverage for the touched script plus tests is `99.06%` (`105/106`),
       `make integration-test` passes with `70 passed in 924.47s (0:15:24)`, and `git diff --check`
       passes

## Acceptance

- a single repository-owned smoke command proves desktop token smoothing, banner priority,
  download-recovery restore, and navigation grounding
- the smoke payload is validated by both unit-level script tests and an integration test
- contributors have a dedicated runbook that explains how to run the smoke and interpret failures

## Risks

- if the smoke only checks `RuntimeViewModel` state without rendering SwiftUI surfaces, future
  navigation regressions can hide behind view-model-only coverage
- if the script invents its own payload instead of forwarding the Swift smoke output, the runbook
  and integration test can drift from the actual desktop evidence contract
- if new runbook material lands without a dedicated smoke command, `M15.4` will still rely on
  unwritten manual operator knowledge
