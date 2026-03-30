# M17.4 Speech Integration Benchmarks, Runbooks, And Operator Evidence

## Goal

Leave speech support with real integration evidence, benchmark data, and operator guidance across transcription and synthesis paths.

## Scope

- add live-path integration coverage for transcription and synthesis
- record backend-family and voice-specific metrics
- document operator workflows, dependency setup, and failure diagnosis

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Benchmarks should distinguish backend family and voice family so operator guidance stays actionable.
- Runbooks should include missing-dependency diagnosis and locale or voice fallback inspection.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Speech integration coverage is live-path and reproducible.
- Metrics and runbooks provide concrete operator evidence for supported speech backend families.
