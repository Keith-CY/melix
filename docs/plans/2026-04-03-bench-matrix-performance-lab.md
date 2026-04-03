# Bench Matrix Performance Lab Plan

## Goal

Add an experimental `bench matrix` workflow on top of the current product-facing `bench run` and `eval run` surfaces.

The new workflow must provide:

- a distinct CLI surface under `melix bench matrix`
- a dedicated control-plane and worker execution path
- persisted matrix summaries and request-level observations
- Window UI support for launching and reviewing matrix runs
- CSV export for summary rows and request rows

## Architecture

Keep `bench run` unchanged as the operator-facing benchmark path.

Add a parallel `bench matrix` path with:

- Swift control plane as orchestration truth for target resolution, parameter normalization, and run-history shaping
- Python worker as execution truth for matrix cell expansion, repeated probes, sustained-load execution, and artifact persistence
- shared export-bundle support for matrix history without mixing matrix rows into the product benchmark summary tables

## Execution Slices

### Slice 1: Contract And Planning Reset

- update `docs/benchmark-evaluation-contract.md` so `bench matrix` is a canonical workflow rather than a future possibility
- add this execution plan
- reset `task_plan.md` to the new transaction

### Slice 2: Protocol, CLI, And Control Plane

- extend control-plane and worker protobufs with `RunBenchMatrix` request and reply surfaces
- add `melix bench matrix run/list/export-summary-csv/export-requests-csv`
- add control-plane validation for matrix inputs, explicit load-budget rules, and benchmark-mode persistence

### Slice 3: Worker Runner, Persistence, And Export

- add a matrix runner that expands parameter cells and records repeated request observations
- persist matrix summaries and request rows under a dedicated matrix output root
- extend export-bundle assembly with matrix history, summary rows, and request rows

### Slice 4: Window UI

- add `Standard / Matrix` mode selection inside the Bench surface
- add matrix controls, history, summary views, and CSV export actions
- keep matrix state and derived presentation separate from existing product benchmark metric cards and charts

### Slice 5: Verification And Close-Out

- run focused changed-line coverage for CLI, control plane, worker, and Window UI scopes
- run `make proto`, `make py-test`, `make swift-test`, and `make integration-test`
- update `progress.md`, `task_plan.md`, and the benchmark runbook with final evidence

## Acceptance

- `melix bench matrix run` supports matrix inputs for context, generation length, batch, cache, reasoning, structured output, and concurrency
- matrix jobs persist explicit `benchmark_mode = matrix`
- matrix summary and request CSV exports are available from CLI and Window UI
- Window UI can start, inspect, and export matrix runs without regressing the existing `bench run` surface
- changed-line coverage is at or above `95%` for the touched executable scope before each commit

## Risks

- matrix execution can create combinatorial expansion, so preflight guardrails are required before worker dispatch
- adding matrix history into shared export surfaces can regress existing benchmark or evaluation history unless matrix rows are kept explicitly separate
- concurrency-oriented probes can create timing-sensitive tests, so deterministic fixtures and bounded fake runtimes should be preferred for default coverage
