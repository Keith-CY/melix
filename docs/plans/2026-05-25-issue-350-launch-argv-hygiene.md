# Issue 350 Launch Argv Hygiene

## Goal

Add a focused server-session launch argv hygiene guard for serving acceleration
profiles so parser input, CLI command previews, and subprocess-ready argv use
the same registered split-form flags.

## Scope

- Accept `--flag=value` forms for existing server-session mutation options that
  can arrive from saved previews, copied shell snippets, or stale operator
  state.
- Normalize those inputs into the same `MelixCLICommand` values produced by
  split-form flags.
- Keep `MelixCLICommandCodec.arguments(for:)` as the preview/runtime argv source
  of truth, and assert it emits registered split-form flags rather than
  preserving equals-form input.
- Cover profile-owned launch settings:
  - `--acceleration-profile`
  - `--acceleration-mode`
  - `--draft-model-id`
  - `--num-draft-tokens`
- Cover adjacent server-session launch controls that should share the same
  parser/codec parity boundary:
  - `--model`
  - `--models`
  - `--default-model`
  - `--host`
  - `--port`
  - `--rate-limit-per-minute`
  - `--timeout-seconds`
  - `--model-idle-timeout-seconds`
  - `--server-session-id`

## Out Of Scope

- Adding a new advanced-args UI.
- Passing arbitrary unknown worker/runtime flags.
- Changing runtime launch behavior, request dispatch, or acceleration profile
  admission.
- Adding production observability counters. This is a command-shaping guard.

## Design

`ArgumentCursor` remains the central CLI option parser. The parser will split a
token shaped as `--option=value` into the same option/value pair it would have
received from `--option value`, while preserving value-less flags such as
`--json`. A token `--option=` is treated as an explicit empty value so existing
validation paths can reject required values or blank profile fields with their
current typed errors.

The command codec continues to emit only split-form argv through
`appendOption`/`appendPositiveInt`. Tests parse equals-form server session
create and update commands, then round-trip them through
`MelixCLICommandCodec.arguments(for:)` to prove preview/runtime argv is stable,
registered, and free of stale equals-form launch flags.

## Verification

- Red/green Swift parser test:
  `swift test --filter 'MelixCLIParserTests/serverSessionCodecNormalizesEqualsFormProfileLaunchFlags'`
- Focused parser suite:
  `swift test --filter 'MelixCLIParserTests'`
- Diff hygiene:
  `git diff --check`
- PR-scoped performance report for changed files, expected to select no direct
  runtime probes or only Swift CLI command-shaping probes with zero regressions.

## Metrics

This parser-only slice changes command normalization before any server session
is launched. It does not add request-path runtime work, model loading,
diagnostics queue serialization, or worker instrumentation. Success metrics are
deterministic parser/codec parity and a PR-scoped performance report with zero
direct regressions.
