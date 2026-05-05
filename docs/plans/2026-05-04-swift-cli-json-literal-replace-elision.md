# Swift CLI JSON metric literal replace-elision slice

## Scope

This Swift performance slice is limited to CLI JSON metric literal encoding in `Sources/MelixCLICore/MelixCLIJSON.swift`.

Touched paths:

- `Sources/MelixCLICore/MelixCLIJSON.swift`
- `docs/plans/2026-05-04-swift-cli-json-literal-replace-elision.md`

## Goal

Avoid a redundant full-string pass in `MelixCLIJSONMetricPatch.literal(for:)`. The formatter already uses the lowercase `%e` exponent marker under the fixed `en_US_POSIX` locale, so the follow-up `.replacingOccurrences(of: "E", with: "e")` scans every encoded metric literal without changing the result.

## Registered probe

The affected Swift path is covered by registered PR-scoped probe `swift-cli-json-envelope-encoding` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and runs on the `macos-15` GitHub Actions runner because Swift tooling is not available in the Linux cron environment.

## Linux validation boundary

This cron environment has no `swift` binary, so local validation is limited to repository inspection and command-toolchain detection. The Swift behavior and performance effect must be validated by the registered macOS PR-scoped performance CI probe before merge.

## Implementation plan

1. Keep the existing `%e` / `en_US_POSIX` formatter contract.
2. Remove only the redundant uppercase-to-lowercase replacement pass.
3. Rely on the registered macOS focused tests and probe for behavior and performance validation.

## Success metrics

- Registered macOS focused tests pass.
- Registered PR-scoped probe `swift-cli-json-envelope-encoding` completes successfully.
- CI probe reports non-regressed `elapsed_ms_mean` for JSON envelope encoding.
