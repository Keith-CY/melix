# Task Plan

## Goal

Close `M10.4` by adding live integration evidence, reproducible lifecycle metrics, and operator
runbook guidance for pause, idle-to-sleep, wake, and lifecycle-fault recovery across the Melix
session-lifecycle surface.

## Scope

- add integration coverage for lifecycle mutations, idle-policy-driven sleep, restart recovery, and
  wake-to-ready flows using the repository-owned session lifecycle paths
- capture machine-readable lifecycle smoke metrics and reproducible evidence for pause, sleep, wake,
  and restart timing boundaries
- document operator diagnosis and recovery steps so the runbook separates reconnect noise from
  genuine lifecycle faults

## Measurement Points

- lifecycle smoke evidence must record pause acknowledgement, idle-to-sleep delay, wake-to-ready
  delay, and restart recovery timing in machine-readable form
- integration coverage must exercise the same control-plane-owned lifecycle paths surfaced in the
  Window UI and CLI rather than using private test-only state mutation shortcuts
- the runbook must point operators to authoritative diagnostics, metrics, and recovery decisions
  for paused, sleeping, stopped, and failed runtime-session states

## Phases

1. Lifecycle smoke and metrics harness
   - status: pending
   - evidence:
     - inspect the existing integration harnesses and session-lifecycle metrics plumbing to locate
       the narrowest place to add reproducible pause, sleep, wake, and restart evidence
     - define the smoke payload and output format so the touched scope can report machine-readable
       lifecycle timings without ad-hoc parsing
2. Integration coverage and operator runbook
   - status: pending
   - evidence:
     - add integration or smoke coverage for lifecycle mutation, idle-policy sleep, wake, and
       restart flows against the repository-owned runtime stack
     - update runbook guidance with diagnosis and recovery steps grounded in authoritative lifecycle
       metrics and runtime-session states
3. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - run the touched integration and documentation verification commands plus repository-default
       verification as needed for the changed scope
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M10.4`
       completed only after evidence is captured

## Acceptance

- the session-lifecycle milestone has reproducible live-path coverage for pause, sleep, wake, and
  restart recovery
- lifecycle metrics are machine-readable, stored with the touched smoke or integration outputs, and
  suitable for later release-gate consumption
- runbooks explain how operators should inspect lifecycle faults and choose recovery actions

## Risks

- relying only on unit-level lifecycle coverage would leave `M10` without proof that the integrated
  runtime stack honors pause, idle sleep, and wake behavior end to end
- metrics that are not machine-readable would make later release-gate automation and regression
  tracking unreliable
- runbook guidance that does not distinguish reconnect churn from genuine lifecycle faults would
  confuse operators and weaken milestone evidence

## Outcome

- m10_4_session_lifecycle_integration_evidence_in_progress
