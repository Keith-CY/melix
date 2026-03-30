# M14.4 Image Iteration Integration And Artifact-Lineage Evidence

## Goal

Close image iteration with live-path integration coverage, lineage evidence, and operator runbook material.

## Scope

- add integration coverage for vary, iterate, and redo flows
- record artifact-lineage and timeout metrics
- document operator workflows for iterative image use

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should prove that prior-artifact iteration remains visible in job and artifact metadata.
- Metrics should separate baseline generation from iterative follow-up requests.
- Runbooks should cover retry, timeout, and lineage inspection flows.

## Verification

- `make integration-test`
- image-iteration smoke command for the touched scope

## Acceptance

- Iterative image workflows have live integration coverage and reproducible lineage evidence.
- Operators can reproduce the documented iterate and redo flows from repository artifacts alone.
