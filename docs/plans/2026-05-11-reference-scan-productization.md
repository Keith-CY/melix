# Reference Scan Productization Plan

## Goal

Close GitHub issue [#643](https://github.com/Keith-CY/melix/issues/643) by
turning the Sparrow and LocalAI scan into a durable Melix documentation artifact
with clear follow-up issue mapping, priority order, adoption guardrails, and
probe expectations.

## Scope

- Add `docs/reference-scans/sparrow-localai-lessons.md`.
- Link the scan from `docs/README.md`.
- Record how the scan maps to follow-up issues #636 through #642.
- Preserve the issue-level priority order without pretending the follow-up
  features have been implemented.

## Non-Goals

- Do not implement #636, #637, #638, #639, #640, #641, or #642 in this plan.
- Do not import code, schemas, recipes, or runtime behavior from Sparrow or
  LocalAI.
- Do not broaden Melix beyond the local-first Apple Silicon runtime scope.

## Design Notes

The scan is a product and architecture reference. It should be useful to future
implementation work without becoming a dependency on the scanned repositories.

The documentation must make three boundaries explicit:

1. Sparrow and LocalAI are references, not code sources.
2. #643 closes only the scan-recording task.
3. Runtime probe and metrics requirements belong to each follow-up
   implementation plan.

## Probe And Metrics Plan

This change is documentation-only and has no touched runtime path, so no runtime
performance probe is added here.

The scan document must still define probe expectations for each follow-up issue
so downstream implementation plans start with measurable success criteria.

Docs-level success metrics:

- The scan document exists and links every follow-up issue.
- The docs index links the scan.
- `git diff --check` passes.
- The pull request evidence body validates successfully.

## Implementation Steps

1. Create the reference scan document under `docs/reference-scans/`.
2. Update `docs/README.md` with a `Reference Scans` entry.
3. Validate formatting and PR evidence.
4. Open a pull request that closes #643.

## Acceptance

- `docs/reference-scans/sparrow-localai-lessons.md` records sources, findings,
  priority order, adoption guardrails, and probe expectations.
- `docs/README.md` links the scan.
- The PR body includes `Closes #643`.
- Verification output states that coverage and runtime metrics are `N/A` because
  this is documentation-only.
