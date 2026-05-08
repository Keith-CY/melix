# Plan 5: PR And Release Evidence Gate

## Goal

Make PR and release evidence consume structured reports and fail clearly when
required evidence, probes, telemetry, or gate metrics are missing.

## Scope

- Add report JSON verification to PR evidence workflows.
- Define the minimum release evidence matrix.
- Classify gate, informational, and known-gap metrics.
- Keep all evidence local, repository-owned, or CI-artifact backed.

## Implementation Notes

- Release evidence should include serving benchmark, dialogue/event evaluation,
  adapter checks, and runtime checks.
- PR evidence should link the generated Markdown report and the machine-readable
  report JSON path.
- Gate failures should report blocking metrics and the slowest relevant probe
  phases.
- Telemetry failures should be explicit and may fail release gates when the
  selected gate requires hardware evidence.
- Do not add public leaderboard submission, identity sharing, or community
  upload endpoints.

## Verification

- Verifier tests for complete and incomplete reports.
- Release-gate fixture that emits pass, fail, informational, and known-gap
  results.
- PR-body evidence validation using the repository PR template headings.
- Smoke command that generates a PR-ready evidence bundle.

## Acceptance

- PR evidence cannot pass with missing run identity, target identity, probe
  timeline, telemetry summary, or required gate policy.
- Release evidence explains both result regressions and likely responsible
  runtime phases.
- No public submission path is introduced.
