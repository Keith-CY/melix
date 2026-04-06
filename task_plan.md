# Task Plan

## Goal

Backfill child-level `M7.1-M7.10` execution-index status so the repository records the already
landed benchmark and evaluation closure per child milestone instead of only through the parent `M7`
summary and later umbrella plans.

## Scope

- add explicit completed status lines for `M7.1` through `M7.10` in the execution index
- record the docs-only closure in `progress.md` with an explicit `N/A` metrics report
- keep the transaction limited to execution-index accuracy rather than reopening benchmark code

## Measurement Points

- `M7.1-M7.10` each have child-level completed status in the execution index
- the progress log records the backfill as a docs-only bookkeeping transaction
- `git diff --check` passes and no executable files change

## Phases

1. Boundary lock and evidence readback
   - status: in_progress
   - success criteria:
     - confirm the parent `M7` summary, progress log, and later follow-up plans provide enough
       evidence to state child-level completion without reopening implementation work
2. Execution-index child-status backfill
   - status: pending
   - success criteria:
     - add concise completed status lines for `M7.1` through `M7.10`
     - keep the wording aligned with the repository-owned benchmark, evaluation, export, VLM, and
       release-gate work already landed
3. Progress and metrics note
   - status: pending
   - success criteria:
     - record the docs-only closure in `progress.md`
     - include an explicit `N/A` metrics report because no executable scope changed
4. Commit and next-gap audit
   - status: pending
   - success criteria:
     - submit a GPG-signed docs-only commit
     - continue triaging the next milestone area whose status still lacks repository evidence

## Acceptance

- `M7.1-M7.10` are no longer ambiguous child entries under a completed parent milestone
- the transaction remains docs-only and explicitly reports `N/A` executable metrics
- the next audit can focus on truly unresolved milestones instead of benchmark bookkeeping drift

## Risks

- if child-level status lines overclaim beyond the recorded repository evidence, the execution
  index will become misleading
- if this transaction expands past index bookkeeping, it will blur the line between status repair
  and new benchmark work
