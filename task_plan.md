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
   - status: completed
   - evidence:
     - matrix runs persist under `<jobs_root>/bench/matrix-runs/<job_id>/`
     - worker responses expose typed matrix job summaries plus summary rows
     - export and submission bundles now carry matrix jobs, summary rows, and request rows
4. Slice 4: Window UI matrix controls and result views
   - status: completed
   - evidence:
     - the diagnostics workspace now exposes a `Standard / Matrix` mode switch inside the Bench surface
     - matrix runs can be launched from Window UI with explicit generation length, cache, reasoning, structured-output, concurrency, and load-budget controls
     - matrix history, summary cards, charts, and CSV export actions are now available without regressing the existing product benchmark path
5. Slice 5: verification, coverage, and documentation close-out
   - status: completed
   - evidence:
     - repository-owned benchmark runbook now documents `bench matrix` alongside the existing benchmark and evaluation flows
     - focused changed-line coverage was rerun across CLI, control plane, Python worker, Window UI, and the Swift text-worker follow-up scope
     - `make proto`, `make py-test`, `make swift-test`, and `make integration-test` all completed successfully during the close-out slice

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
  - Slice 4 closed with Window UI matrix controls, history, charts, and export actions
- remaining slices:
  - none; the `bench matrix` transaction is closed
