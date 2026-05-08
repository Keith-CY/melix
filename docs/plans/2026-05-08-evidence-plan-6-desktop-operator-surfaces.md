# Plan 6: Desktop Operator Evidence Surfaces

## Goal

Expose run evidence, reports, probe timelines, Apple Silicon telemetry, and
runtime diagnostics in the macOS operator app.

## Scope

- Add read-only Run History, Report, Runtime Diagnostics, and Hardware Monitor
  surfaces.
- Keep structured evidence and report artifacts as the only data source.
- Support operator inspection and export without log parsing.

## Implementation Notes

- Run History shows run status, target, runtime, adapter, key metrics, and
  artifact links.
- Report surfaces read report JSON and expose filtering, sorting, Markdown
  opening, and CSV export.
- Runtime Diagnostics shows probe timeline summaries, phase duration, component
  attribution, error stage, skipped phases, and fallback phases.
- Hardware Monitor shows CPU, GPU, memory, power, frequency, thermal, and
  process attribution, with current-run association where available.
- UI state must not create or mutate evidence truth.

## Verification

- Swift view-model tests for evidence, report, probe, telemetry, and process
  decoding.
- UI acceptance for completed, failed, fallback, and telemetry-failure runs.
- Export/open smoke tests for Markdown and CSV derived artifacts.

## Acceptance

- Operators can diagnose a run from the app without opening raw logs.
- UI displays probe and telemetry gaps or failures explicitly.
- All views are derived from structured artifacts.
