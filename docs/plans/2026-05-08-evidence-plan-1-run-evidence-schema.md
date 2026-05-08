# Plan 1: Unified Run Evidence Schema

## Goal

Create the single structured evidence envelope used by benchmark, evaluation,
event extraction, adapter/runtime checks, reports, and release gates.

## Scope

- Define the evidence JSON schema.
- Attach domain-specific benchmark and evaluation results to the envelope.
- Require probe timeline and Apple Silicon telemetry summary fields.
- Make the new schema the only supported evidence input for new reports.

## Implementation Notes

- Add repository-owned schema/types for the evidence envelope across protocol,
  worker productization, and Swift decoding.
- Include identity, target, runtime, adapter, dataset, status, metrics, probes,
  telemetry, artifacts, failure, and fallback fields from
  `docs/evidence-telemetry-report-contract.md`.
- Keep benchmark and evaluation domain payloads separate inside the common
  envelope so score semantics do not drift into performance metrics.
- Ensure artifact paths are relative to the run artifact root or repository
  root.

## Verification

- Schema roundtrip tests for completed, failed, cancelled, and fallback runs.
- End-to-end fixture evidence for one serving benchmark and one evaluation run.
- Verifier fixture that rejects evidence missing run identity, target identity,
  probe timeline, or telemetry summary.

## Acceptance

- New benchmark and evaluation evidence artifacts use the unified envelope.
- Reports and gates consume evidence JSON rather than parsing logs or Markdown.
- Missing required evidence fields fail verification.
