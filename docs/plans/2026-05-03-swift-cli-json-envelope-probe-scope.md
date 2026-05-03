# Swift CLI JSON Envelope Probe Scope Optimization

## Goal

Reduce `swift-cli-json-envelope-encoding` PR-scoped performance CI runtime by
running only the Swift CLI JSON envelope tests that govern the probe, instead of
running the full `MelixCLIRunnerTests` suite for verification and base/head
measurement.

## Context

The probe currently watches `Sources/MelixCLICore/MelixCLIJSON.swift` and
`tests/MelixCLITests/MelixCLIRunnerTests.swift`, but its `test_command`,
`coverage_command`, and `probe_command` all run
`swift test --filter MelixCLITests/MelixCLIRunnerTests`. Because
`coverage_replays_tests` only skips the standalone test command, the macOS probe
still runs the full runner suite three times: once for head verification, once
for base measurement, and once for head measurement.

## Scope

- Update `infra/perf/pr_scoped_probes.json`.
- Keep the existing probe id, runner, metric, watch globs, and
  `coverage_replays_tests` behavior.
- Use a focused Swift verification filter covering:
  - JSON v1 success envelopes
  - JSON v1 error envelopes
  - metric placeholder rejection paths
  - sentinel-like artifact strings
- Use a base/head measurement filter covering the envelope encode paths that
  pass on both the base and head checkouts. The head verification gate keeps the
  metric placeholder rejection coverage, while the measurement command avoids
  letting the known baseline uppercase-exponent behavior fail the base probe.
- Stream long Swift command output to the GitHub Actions log and emit probe
  phase progress so macOS runs do not appear stalled during cold builds.

## Success Criteria

- Focused Swift filter runs the intended JSON envelope tests.
- PR-scoped performance registry JSON remains valid.
- The focused probe entry still exposes non-empty test, coverage, and probe
  commands through `test_registered_probes_expose_focused_commands`.
- The CI runner emits start, heartbeat, and completion messages for long-running
  probe commands.
- The local command surface used for this change passes where the local Swift
  toolchain is available.
