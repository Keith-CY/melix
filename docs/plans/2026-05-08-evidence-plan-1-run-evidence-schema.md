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

## Implementation Status

- Serving benchmark and evaluation persistence now write `run-evidence.json`
  beside the existing run artifacts.
- Worker and control-plane protobuf APIs now carry `evidence_path` for serving
  benchmark and evaluation results so downstream clients can locate the
  structured evidence envelope without parsing report Markdown.
- Export bundles now include a top-level `run_evidence` array collected from
  benchmark and evaluation runs, with Swift decoding support for the envelope,
  metrics, probes, telemetry summary, artifacts, fallback, failure, and domain
  result payloads.
- The initial envelope records an `artifact_write` probe and an explicit
  `not_collected` Apple Silicon telemetry summary until Plan 2 and Plan 3 add
  full stage probes and hardware sampling.
- Full report JSON generation and release-gate enforcement remain in Plan 4
  and Plan 5; this plan provides the required source evidence artifact and
  transport path for those consumers.

## Verification

- Schema roundtrip tests for completed, failed, cancelled, and fallback runs.
- End-to-end fixture evidence for one serving benchmark and one evaluation run.
- Verifier fixture that rejects evidence missing run identity, target identity,
  probe timeline, or telemetry summary.

## Acceptance

- New benchmark and evaluation evidence artifacts use the unified envelope.
- Reports and gates consume evidence JSON rather than parsing logs or Markdown.
- Missing required evidence fields fail verification.
