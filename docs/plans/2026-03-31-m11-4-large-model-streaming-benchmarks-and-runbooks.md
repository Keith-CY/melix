# M11.4 Large-Model Streaming Benchmarks And Runbooks

## Goal

Leave disk streaming with reproducible operator evidence for large-model startup, steady-state, and recovery behavior.

## Scope

- add benchmark and smoke coverage for streamed sessions
- record SSD-backed latency and throughput metrics
- document operator setup and diagnosis workflows

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should separate RAM-resident baselines from streamed-session behavior.
- Runbooks should document budget tuning, recovery expectations, and cache-policy interpretation.
- Metrics should remain suitable for future release gates.

## Verification

- `make integration-test`
- streaming-benchmark smoke command for the touched scope

## Acceptance

- Disk-streaming mode has reproducible performance evidence and operator runbooks.
- Large-model streaming diagnostics are documented and test-backed.
