# Swift CLI JSON metric literal lowercase-exponent elision slice

## Scope

This Swift performance slice is limited to CLI JSON metric literal encoding in `Sources/MelixCLICore/MelixCLIJSON.swift`.

Touched paths:

- `Sources/MelixCLICore/MelixCLIJSON.swift`
- `docs/plans/2026-05-04-swift-cli-json-literal-replace-elision.md`

## Goal

Avoid a redundant exponent scan in `MelixCLIJSONMetricPatch.literal(for:)`. The
formatter already uses the lowercase `%e` conversion with `en_US_POSIX`, so the
stable JSON metric literal contract can return the formatted string directly
without checking for an uppercase exponent marker on every CLI JSON envelope.

## Registered probe

The affected Swift path is covered by registered PR-scoped probe `swift-cli-json-envelope-encoding` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and runs on the `macos-15` GitHub Actions runner because Swift tooling is not available in the Linux cron environment.

## Linux validation boundary

This cron environment has no `swift` binary, so local validation is limited to repository inspection and command-toolchain detection. The Swift behavior and performance effect must be validated by the registered macOS PR-scoped performance CI probe before merge.

## Implementation plan

1. Keep the existing `%e` / `en_US_POSIX` formatter contract.
2. Return the formatted metric literal directly and remove the now-redundant
   uppercase-exponent scan.
3. Rely on the registered macOS focused tests and probe for behavior and performance validation.

## Success metrics

- Registered macOS focused tests pass.
- Registered PR-scoped probe `swift-cli-json-envelope-encoding` completes successfully.
- CI probe reports non-regressed `elapsed_ms_mean` for JSON envelope encoding.
