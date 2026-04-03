# Task Plan

## Goal

Execute `docs/plans/2026-04-03-bench-eval-contract-expansion-implementation.md` so Melix benchmark and evaluation flows match `docs/benchmark-evaluation-contract.md`.

## Scope

- complete protocol expansion for canonical `bench` and `eval` inputs
- normalize canonical bench request handling across CLI and control plane
- implement worker-side benchmark sweeps, metrics, and export shapes
- implement evaluation controls, persistence, and export shapes
- productize the new controls in the Window UI
- close the transaction with verification, coverage, and updated repository records

## Phases

1. Task 1: extend protocol surfaces for canonical bench and eval inputs
   - status: completed
   - evidence: `ed65fe6`
2. Task 2: implement canonical bench request normalization in CLI and control plane
   - status: completed
   - evidence: `d70d4a2` and `769f65b`
3. Task 3: implement canonical bench metrics, sweeps, and exports in the Python worker
   - status: completed
   - evidence: `497330a` and `f109442`
4. Task 4: implement canonical evaluation controls, persistence, and exports
   - status: pending
5. Task 5: productize bench and eval controls in Window UI
   - status: pending
6. Task 6: run full verification, update docs, and close the transaction
   - status: pending

## Acceptance

- protocol request surfaces include the canonical fields from `docs/benchmark-evaluation-contract.md`
- `bench run` normalizes repeated context and batch inputs before worker dispatch
- invalid bench cache profiles are rejected at the CLI and control-plane boundary
- the active transaction keeps changed-line coverage at or above `95%` for touched executable scope before each commit

## Risks

- the transaction spans CLI, shared client, control plane, worker, and Window UI, so partial commits can leave the contract temporarily split across layers
- benchmark and evaluation productization share export surfaces, so schema drift can appear if the later worker tasks are landed without matching tests

## Outcome

- completed slices:
  - landed Task 1 protocol expansion for canonical bench and eval inputs
  - landed Task 2 canonical bench request normalization across CLI and control plane
  - landed Task 3 canonical benchmark sweeps, truthful batch-row behavior, and export expansion in the Python worker
- remaining slices:
  - evaluation persistence and export controls
  - Window UI productization
  - transaction-wide verification and close-out
