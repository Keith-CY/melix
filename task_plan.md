# Task Plan

## Goal

Capture the next-generation Melix benchmark and evaluation I/O contract as a canonical repository specification.

## Scope

- add a top-level canonical specification for `bench` and `eval`
- define required inputs, outputs, export shapes, and UI and CLI parity rules
- align the documentation index with the new specification
- record this docs-only transaction in `progress.md`

## Phases

1. Review the current benchmark and evaluation redesign plan and existing runbooks
   - status: completed
2. Write the canonical benchmark and evaluation contract
   - status: completed
3. Update documentation index and transaction records
   - status: completed
4. Commit the docs-only contract capture
   - status: pending

## Acceptance

- `docs/benchmark-evaluation-contract.md` exists as a canonical specification
- the specification defines the Melix `bench run` and `eval run` input and output contract
- the documentation map lists the new specification as canonical
- `progress.md` records the docs-only transaction and explicitly marks metrics coverage as `N/A`

## Risks

- the contract must stay implementation-agnostic enough to survive future backend changes while remaining specific enough for CLI, Window UI, and export compatibility

## Outcome

- completed slices:
  - documented the canonical split between `bench` and `eval`
  - defined task kinds, input fields, output fields, history shape, and export formats
  - defined Window UI and CLI parity expectations
- remaining slices:
  - commit the docs-only contract capture
