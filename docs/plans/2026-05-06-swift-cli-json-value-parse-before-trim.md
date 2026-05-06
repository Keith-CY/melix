# Swift CLI JSON Value Parse Before Trim

## Goal

Reduce avoidable string allocation in the `--output json-v1` CLI envelope path while preserving the existing fallback behavior for plain-text command output.

## Slice

`MelixCLIJSON.jsonValue(from:)` previously trimmed command output before attempting JSON parsing. `JSONSerialization` accepts leading and trailing whitespace, so JSON command output can be parsed directly from UTF-8 bytes and only pay the trimming cost on the non-JSON fallback path.

This slice keeps scope limited to:

- `Sources/MelixCLICore/MelixCLIJSON.swift`
- `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- `infra/perf/pr_scoped_probes.json`

## Registered Probe

The affected Swift path is covered by the existing registered PR-scoped probe:

- `swift-cli-json-envelope-encoding`
- runner: `macos-15`
- test/coverage/probe command: focused `MelixCLIRunnerTests` filter for JSON v1 envelope behavior and metric patching

This slice keeps the existing focused filter unchanged and adds the direct-parse/fallback assertions inside `jsonV1WrapsCommandResultsInAStableEnvelope`, which is already part of the registered test, coverage, and probe commands.

## Verification Plan

Local Linux cannot run Swift in this scheduled environment because `swift` is not installed. Local verification is limited to static repository checks and JSON registry parsing. The registered macOS CI probe is the source of truth for Swift runtime performance validation.

Required CI evidence before merge:

1. focused Swift test command from `swift-cli-json-envelope-encoding` passes on macOS,
2. focused coverage command replays the same tests,
3. registered probe emits `elapsed_ms_mean`, and
4. PR checks are green.

## Expected Performance Direction

For JSON command output, this avoids building a trimmed `String` before converting back to bytes for JSON parsing. Plain-text fallback output still trims exactly as before.
