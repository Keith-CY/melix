# Task Plan

## Goal

Execute `docs/plans/2026-04-03-bench-matrix-performance-lab.md` so Melix gains an experimental `bench matrix` workflow without regressing the product-facing `bench run` and `eval run` contracts.

## Scope

- reset the benchmark contract so `bench matrix` is a canonical workflow
- add protocol, CLI, and control-plane support for matrix runs
- implement worker-side matrix execution, persistence, and export
- add Window UI support for launching and reviewing matrix runs
- close the transaction with verification, coverage, and updated repository records

## Phases

1. Slice 1: contract and planning reset
   - status: completed
   - evidence: current docs-only transaction bootstrap
2. Slice 2: protocol, CLI, and control-plane support for bench matrix
   - status: completed
   - evidence:
     - `RunBenchMatrix` landed across control-plane and worker protocol surfaces
     - `melix bench matrix run|list|export-summary-csv|export-requests-csv` landed in the shared CLI
     - control-plane validation, export decoding, Python bridge, and local XPC client paths are verified with changed-line coverage above `95%`
3. Slice 3: worker-side matrix runner, persistence, and export
   - status: in progress
4. Slice 4: Window UI matrix controls and result views
   - status: pending
5. Slice 5: verification, coverage, and documentation close-out
   - status: pending

## Acceptance

- `bench run` remains the operator-facing benchmark path
- `bench matrix` uses a distinct command surface and export schema
- matrix runs persist explicit `benchmark_mode = matrix`
- Window UI and CLI can both launch and export matrix runs
- the active transaction keeps changed-line coverage at or above `95%` for touched executable scope before each commit

## Risks

- matrix parameter combinations can explode the run count, so preflight guardrails are required
- shared export surfaces can drift if matrix rows are not kept separate from product benchmark rows
- concurrency-oriented probes can make tests flaky unless deterministic harnesses and bounded fixtures are used

## Outcome

- active slices:
  - Slice 1 reset the canonical contract and execution plan for `bench matrix`
  - Slice 3 worker execution, persistence, and export are implemented and being closed with coverage and commit hygiene
- remaining slices:
  - worker-side matrix execution and export
  - Window UI productization
  - transaction-wide verification and close-out
