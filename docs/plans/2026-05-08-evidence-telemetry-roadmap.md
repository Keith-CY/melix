# Evidence, Telemetry, And Report Roadmap

## Goal

Turn Melix benchmark and evaluation output into a structured product evidence
system with first-class probes, Apple Silicon power telemetry, comparison
reports, release gates, and desktop operator surfaces.

The canonical contract is `docs/evidence-telemetry-report-contract.md`.

## Design Rules

- Use the current evidence and report schema only.
- Treat breaking schema changes as acceptable during this roadmap.
- Target macOS on Apple Silicon.
- Use one Apple Silicon/macOS telemetry implementation path with no alternate
  collectors.
- Do not build a public leaderboard or community submission API.
- Use structured evidence JSON as the source of truth.
- Derive Markdown, CSV, UI views, and PR summaries from structured artifacts.

## Execution Plans

1. `docs/plans/2026-05-08-evidence-plan-1-run-evidence-schema.md`
   - Define the unified run evidence envelope.
2. `docs/plans/2026-05-08-evidence-plan-2-runtime-attribution-probes.md`
   - Add runtime attribution and full stage probes.
3. `docs/plans/2026-05-08-evidence-plan-3-apple-silicon-power-telemetry.md`
   - Add Apple Silicon hardware telemetry and process attribution.
4. `docs/plans/2026-05-08-evidence-plan-4-reports-comparison-export.md`
   - Generate report JSON, Markdown, CSV, and comparison outputs.
5. `docs/plans/2026-05-08-evidence-plan-5-pr-release-evidence-gate.md`
   - Wire structured reports into PR and release evidence gates.
6. `docs/plans/2026-05-08-evidence-plan-6-desktop-operator-surfaces.md`
   - Expose evidence, reports, probes, and telemetry in the macOS operator app.

## Dependencies

The evidence schema must land before probes, telemetry, reports, gates, or UI.
Runtime probes should land before report comparison so reports can explain why a
run changed. Telemetry should land before release gates so power regressions can
be classified with the same evidence model as latency and quality regressions.

## Acceptance

- The roadmap points to a canonical contract.
- Every child plan includes probe and telemetry handling where relevant.
- The roadmap excludes public leaderboard work.
- The roadmap keeps hardware telemetry scoped to macOS on Apple Silicon.

## Verification

- Documentation review.
- Link check for all child plan paths.
