# Task Plan

## Goal

Close the remaining `M8.1-M8.4` child-entry bookkeeping gaps so the execution index and each child
plan reflect the already-landed backend-foundations work instead of leaving completion evidence
only at the parent `M8` level.

## Scope

- add top-level completed status summaries to the `M8.1` through `M8.4` child plan documents
- add explicit completed status lines for `M8.1` through `M8.4` in the execution index
- record the docs-only closure in `progress.md` with an explicit `N/A` metrics report

## Measurement Points

- `M8.1`, `M8.2`, `M8.3`, and `M8.4` each have explicit completed status in the execution index
- the four child plan documents each expose a top-level completed status summary
- the progress log records the closure as a docs-only bookkeeping transaction with `git diff --check`
- no executable files or generated artifacts change in this transaction

## Phases

1. Boundary lock and evidence readback
   - status: in_progress
   - success criteria:
     - confirm the `M8.1-M8.4` backend-foundations completion evidence already exists in the
       parent plan and progress log
     - avoid broadening the transaction into `M8.5-M8.11` or unrelated milestone cleanup
2. Child-plan status closure
   - status: pending
   - success criteria:
     - add top-level completed status summaries to `M8.1` through `M8.4`
3. Execution-index and progress closure
   - status: pending
   - success criteria:
     - add child-level completed status lines in the execution index
     - record the docs-only closure in `progress.md` with `N/A` executable metrics
4. Commit and next-gap audit
   - status: pending
   - success criteria:
     - submit a GPG-signed docs-only commit
     - resume auditing the next milestone gap that still needs real implementation work

## Acceptance

- `M8.1-M8.4` are no longer represented as child entries without status
- the transaction remains docs-only and explicitly reports `N/A` executable metrics
- follow-up milestone triage starts from a cleaner execution index

## Risks

- if the child statuses are added without staying aligned to the parent `M8.1-M8.4` handoff note,
  the repository could present conflicting completion narratives
- if this transaction drifts into broader `M8` edits, it will lose the docs-only closure boundary
