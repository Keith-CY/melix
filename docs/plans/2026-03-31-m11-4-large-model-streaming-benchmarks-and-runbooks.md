# M11.4 Large-Model Streaming Benchmarks And Runbooks

## Status

Closed on 2026-04-05 as an evidence-only milestone slice. The repository now owns a truthful
disk-streaming evidence path via the `melix-disk-streaming-smoke` executable, focused Swift smoke
coverage, live integration coverage, and an operator runbook. Both worker paths still reject
`prefer_disk` and `require_disk` with typed `disk_streaming_unsupported` failures, so this slice
intentionally records a numeric RAM baseline plus explicit unsupported-path diagnostics instead of
claiming true SSD-backed restore or throughput execution.

## Goal

Leave disk streaming with reproducible operator evidence for large-model startup, steady-state, and recovery behavior.

## Scope

- add baseline benchmark and unsupported-path smoke coverage for streamed-session requests
- record the streaming diagnostics Melix can measure truthfully today
- document operator setup and diagnosis workflows

## Files

- update `Package.swift`
- add `Sources/MelixCLICore/DiskStreamingSmokeCommand.swift`
- add `Sources/MelixCLICore/DiskStreamingSmokeRunner.swift`
- add `Sources/MelixDiskStreamingSmoke/main.swift`
- update `tests/MelixCLITests/DiskStreamingSmokeRunnerTests.swift`
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
- `swift test --filter DiskStreamingSmokeRunnerTests`
- `swift test --enable-code-coverage --filter DiskStreamingSmokeRunnerTests`
- disk-streaming smoke command for the touched scope

## Acceptance

- The repository owns reproducible smoke evidence for the current disk-streaming surface.
- This slice closes only the evidence and runbook scope; true SSD-backed execution remains future
  runtime work.
- Large-model streaming diagnostics are documented and test-backed without claiming unsupported SSD
  execution exists.
- The smoke report records current RAM-baseline benchmark metrics, typed unsupported-path
  diagnostics for `prefer_disk` and `require_disk`, and explicit placeholder fields for future
  SSD-backed metrics that remain unavailable until runtime support exists.
