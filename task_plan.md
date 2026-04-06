# Task Plan

## Goal

Formalize the parent-level `M6` completion status in the execution index so the repository reflects
the recorded M6 closure evidence without pretending the remaining child-entry backfill has already
been audited.

## Scope

- add an explicit completed status line to the `M6` section in the execution index
- add a top-level status section to `docs/plans/2026-03-31-m6-completion-closure.md`
- record the docs-only closure in `progress.md` with an explicit `N/A` metrics report

## Measurement Points

- `M6` has a parent-level completed status in the execution index
- the M6 closure document exposes a top-level completed status summary
- the progress log records the transaction as docs-only with `git diff --check`
- no executable files or generated artifacts change

## Phases

1. Boundary lock and evidence readback
   - status: in_progress
   - success criteria:
     - confirm the M6 closure document and progress log provide enough evidence for parent-level
       completion language
     - avoid claiming child-level completion for unreviewed `M6.1-M6.6` entries
2. Parent-status formalization
   - status: pending
   - success criteria:
     - add completed status text to the execution-index `M6` section
     - add a top-level completed status section to the M6 closure document
3. Progress and metrics note
   - status: pending
   - success criteria:
     - record the docs-only closure in `progress.md`
     - include an explicit `N/A` metrics report because no executable scope changed
4. Commit and next-gap audit
   - status: pending
   - success criteria:
     - submit a GPG-signed docs-only commit
     - continue auditing `M1-M5` and any remaining child-entry status gaps

## Acceptance

- the repository no longer leaves `M6` without any formal completion status
- the transaction remains docs-only and explicitly reports `N/A` executable metrics
- later audits can decide child-level `M6` status without re-litigating the parent closure

## Risks

- if the parent status overclaims beyond the recorded closure evidence, the execution index will
  misstate M6 readiness
- if this transaction drifts into child-level claims for `M6.1-M6.6`, it will exceed the audited
  evidence boundary
