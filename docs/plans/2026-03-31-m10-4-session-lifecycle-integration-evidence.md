# M10.4 Session Lifecycle Integration Evidence

## Goal

Close the session-lifecycle milestone with live-path coverage, metrics, and operator runbook evidence.

## Scope

- add lifecycle smoke paths and restart coverage
- record pause, sleep, and wake metrics
- document operator diagnosis and recovery steps

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should include idle-to-sleep and wake-to-ready timings.
- Recovery guidance should separate transient reconnect issues from genuine lifecycle faults.
- Metrics must remain machine-readable and reproducible.

## Verification

- `make integration-test`
- session-lifecycle smoke command for the touched scope

## Acceptance

- The session lifecycle has live integration coverage and a reproducible metrics report.
- Runbooks explain how to inspect and recover lifecycle failures.
