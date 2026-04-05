# M11.4 Large-Model Streaming Benchmarks And Runbooks

## Status

In progress on 2026-04-05. The repository now has typed disk-streaming settings, memory-budget
admission, and cache-compatibility surfaces, but both worker paths still reject `prefer_disk` and
`require_disk` with typed `disk_streaming_unsupported` failures. `M11.4` therefore starts by
adding truthful RAM-baseline benchmark evidence, unsupported-path smoke coverage, and operator
runbook guidance while leaving real SSD-backed restore and throughput metrics pending future
runtime support.

## Goal

Leave disk streaming with reproducible operator evidence for large-model startup, steady-state, and recovery behavior.

## Scope

- add baseline benchmark and unsupported-path smoke coverage for streamed-session requests
- record the streaming diagnostics Melix can measure truthfully today
- document operator setup and diagnosis workflows

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should separate RAM-resident baselines from attempted streamed-session behavior.
- Runbooks should document budget tuning, recovery expectations, cache-policy interpretation, and
  the current unsupported-runtime boundary.
- Metrics should remain suitable for future release gates without fabricating unavailable SSD
  measurements.

## Verification

- `make integration-test`
- streaming-benchmark smoke command for the touched scope

## Acceptance

- The repository owns reproducible smoke evidence for the current disk-streaming surface.
- Large-model streaming diagnostics are documented and test-backed without claiming unsupported SSD
  execution exists.
