# Plan 4: Reports, Comparison, And Export

## Goal

Generate report JSON, Markdown, CSV, and comparison output from structured run
evidence.

## Scope

- Define report JSON as the report source of truth.
- Derive Markdown and CSV exports from report JSON.
- Support single-run, comparison, PR evidence, and release-gate report kinds.
- Include probe and Apple Silicon telemetry summaries in every relevant report.

## Implementation Notes

- Include all report sections from
  `docs/evidence-telemetry-report-contract.md`.
- Support baseline comparison across commit, model, adapter, runtime, and
  dataset dimensions.
- Mark each comparison result as `pass`, `fail`, or `informational` according to
  gate policy.
- Include slowest probe phases, failed probe phases, fallback phases, telemetry
  summaries, telemetry failures, and artifact links in Markdown output.
- Split CSV exports into runs, metrics, probe phases, telemetry summary,
  processes, gate results, and comparison deltas.

## Verification

- Golden tests for report JSON, Markdown, and CSV outputs.
- Comparison fixture for baseline versus current evidence.
- Verifier fixture rejecting reports missing required identity, target, metrics,
  probe timeline, telemetry summary, or gate policy.
- Fixture proving telemetry failures are not rendered as zero values.

## Acceptance

- Operators can inspect single-run and comparison reports without reading logs.
- PR and release workflows can verify report JSON.
- Markdown and CSV remain derived views of report JSON.
