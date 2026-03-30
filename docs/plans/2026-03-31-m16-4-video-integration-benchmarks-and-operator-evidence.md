# M16.4 Video Integration Benchmarks And Operator Evidence

## Goal

Leave video understanding with reproducible integration evidence, operator runbooks, and measurable benchmark data rather than only contract-level support.

## Scope

- add live integration coverage for representative video requests
- record preprocessing, routing, and latency metrics
- document operator workflows and recovery paths

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Benchmarks should cover at least one short local video, one remote video path, and one bounded multi-frame workload.
- Operator evidence should include cleanup inspection and background-lane diagnosis.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Video integration coverage is live-path and reproducible.
- Runbooks and metrics reports capture real operator-relevant evidence for video workloads.
