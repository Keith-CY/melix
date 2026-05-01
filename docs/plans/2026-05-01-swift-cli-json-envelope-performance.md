# Swift CLI JSON Envelope Performance Slice

## Summary

Optimize the Swift CLI JSON envelope metric-object assembly path and register a PR-scoped macOS CI probe for the touched Swift files.

## Goals

1. Keep CLI JSON envelope behavior unchanged.
2. Avoid avoidable dictionary growth while assembling envelope metrics.
3. Ensure Swift-only performance slices are covered by the PR-scoped performance CI registry.
4. Use macOS CI as the source of truth for Swift verification because local Linux does not provide the Swift toolchain.

## Scope

- `Sources/MelixCLICore/MelixCLIJSON.swift`
- `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- PR-scoped performance registry/tooling required to run a command-emitted JSON probe.

## Design

`MelixCLIJSONEnvelope` currently converts `[String: Double]` into `[String: Any]` through `reduce(into:)` starting from an empty dictionary, then appends the measured JSON encode placeholder. The first slice introduced a small helper that preallocates `metrics.count + 1` slots and is shared by success and error envelope construction.

The next slice keeps the same JSON literal formatting semantics but stores each generated placeholder's quoted JSON literal and UTF-8 data alongside the token. This avoids rebuilding the same quoted string and `Data` buffer while success/error envelope patching or pipeline placeholder lookup validates uniqueness, while preserving stable placeholder tokens and decimal formatting.

The follow-up literal-format slice keeps the same `%.16e` POSIX formatting contract while dropping the redundant uppercase-exponent replacement pass. The format specifier already requests lowercase scientific notation, so avoiding the second string scan reduces per-envelope metric literal work without changing encoded output.

The PR-scoped performance registry uses a `command_json` probe mode so Swift probes can execute a shell command on a macOS runner and emit JSON metrics without requiring Python to import Swift code directly.

## Success Metrics

- Existing `MelixCLIRunnerTests` continue to pass on macOS CI.
- Registered probe `swift-cli-json-envelope-encoding` runs in PR-scoped performance CI.
- CI reports no probe regression beyond the configured 5% warning threshold. The Swift command-json probe runs the focused debug `swift test` command once per base/head checkout and uses the same command as the pass/fail coverage gate, with `coverage_replays_tests` enabled to avoid a duplicate head verification invocation.

## Known Constraints

- The local development environment is Linux and does not have `swift`; local Swift effect validation is not possible here.
- Swift coverage extraction is not yet normalized into the Python report parser, so the coverage command is used as a pass/fail focused verification gate for this first Swift probe.
