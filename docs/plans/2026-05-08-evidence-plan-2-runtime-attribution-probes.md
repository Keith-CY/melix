# Plan 2: Runtime Attribution And Stage Probes

## Goal

Make every material Melix run explainable by component and phase.

## Scope

- Add structured probes across CLI, control plane, worker, runtime, adapter,
  cache, telemetry, and report generation.
- Record runtime attribution for each run.
- Attach cache, fallback, speculative decode, and DFlash diagnostics to the
  relevant probe phases.

## Implementation Notes

- Use the probe fields and phase names from
  `docs/evidence-telemetry-report-contract.md`.
- Record worker id, runtime kind, runtime process hint, model snapshot, adapter
  id, cache profile, and fallback state in the evidence envelope.
- Write probes directly to the evidence artifact; do not reconstruct them from
  logs after the run.
- Keep probe attributes small and scrubbed of full prompts, responses, dataset
  rows, credentials, and secrets.

## Verification

- Unit tests for probe serialization and parent/child span relationships.
- Integration fixture proving a slow run can be localized to queue, dataset,
  prompt render, adapter load, cache restore, prefill, decode, or report export.
- Fixture coverage for adapter on/off, cache hit/miss, provider fallback, and
  failed phase probes.

## Acceptance

- Every new benchmark and evaluation evidence artifact contains a probe
  timeline.
- Report generation can summarize slowest phases, failed phases, skipped phases,
  and fallback phases.
- Release evidence can point to the responsible component for a regression.
