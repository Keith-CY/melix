# Task Plan

## Goal

Capture the concrete implementation plan for expanding Melix `bench` and `eval` so the running product matches `docs/benchmark-evaluation-contract.md`.

## Scope

- write a staged implementation plan under `docs/plans/`
- decompose protocol, CLI, control-plane, worker, UI, and verification work into commit-sized slices
- update transaction tracking so the repository reflects that the next step is execution, not more contract design

## Phases

1. Review the canonical benchmark and evaluation contract and current redesign plan
   - status: completed
2. Write the executable implementation plan
   - status: completed
3. Update transaction records for the docs-only planning slice
   - status: completed
4. Commit the implementation plan capture
   - status: pending

## Acceptance

- `docs/plans/2026-04-03-bench-eval-contract-expansion-implementation.md` exists
- the plan decomposes the work into protocol, control-plane, worker, UI, and verification tasks
- each task includes concrete files, commands, and commit boundaries
- `progress.md` records this docs-only planning slice with explicit `N/A` coverage

## Risks

- the plan touches multiple subsystems, so execution will need tight commit discipline to avoid mixing protocol, runtime, and UI changes

## Outcome

- completed slices:
  - converted the benchmark and evaluation contract into a commit-sized implementation plan
  - defined exact file targets, probes, verification commands, and commit boundaries
- remaining slices:
  - commit the docs-only implementation plan capture
  - choose the execution approach for the implementation work
