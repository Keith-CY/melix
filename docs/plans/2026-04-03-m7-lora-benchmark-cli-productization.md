# M7, LoRA, Benchmark, And CLI Productization

## Goal

Close the remaining M7 benchmark-platform gaps, make LoRA production-ready across the native operator window and a public `melix` CLI, and then finish Benchmark productization with controlled Hugging Face suites, result visualization, and CSV export.

## Scope

- reset repository progress tracking so the current transaction is explicit and executable
- add a shared local control-plane client surface for both the native operator shell and `melix` CLI
- productize LoRA training with local dataset packages and Hugging Face dataset materialization
- productize adapter activation so derived text models are preserved under stable runtime paths and re-enter serving cleanly
- replace deterministic benchmark placeholder metrics with real serving benchmark execution
- add controlled Hugging Face benchmark suites with on-demand caching and persisted run history
- expose benchmark configuration, history, visualization, and CSV export in the native operator shell and `melix` CLI

## Non-Goals

- implement QLoRA in this transaction
- add a remote or cloud training service
- add arbitrary free-form Hugging Face dataset benchmark execution outside the curated suite catalog
- create a second operator surface that bypasses control-plane state
- add automatic control-plane service bootstrapping to the CLI in v1

## Status

- Slices 1 through 7 are complete in the current transaction.
- Slice 8 remains open for full-repository verification, final metrics capture, and close-out documentation.

## Execution Slices

### 1. Documentation Reset And Transaction Baseline

- update `task_plan.md`, `progress.md`, and the roadmap execution index
- record the active umbrella plan and treat M7 as in progress until the real benchmark runner and evidence land
- commit this slice as documentation only

### 2. Shared Operator Client And CLI Foundation

- move the local control-plane client abstraction into a shared Swift module owned by `MelixControlPlaneCore`
- add a repository-owned `melix` CLI executable with subcommands for LoRA and Benchmark workflows
- keep CLI and Window UI aligned on the same control-plane request and response surfaces

### 3. LoRA Backend Productization

- add dataset-source resolution for `local_package` and `hf_dataset`
- materialize Hugging Face datasets into stable normalized snapshots under the runtime jobs root
- replace temporary output paths with stable per-job paths for `train_lora` and `activate_adapter`
- persist dataset provenance, adapter identity, and derived-model linkage in registry snapshots

### 4. LoRA Window UI And CLI Exposure

- add Window UI forms for model selection, dataset source selection, LoRA hyperparameters, and adapter naming
- add Window UI actions for training, activation, and adapter history inspection
- expose `melix lora train`, `melix lora activate`, and `melix lora list`

### 5. Real Benchmark Runner And M7 Closure

- replace deterministic benchmark placeholder metrics with real execution against an explicitly selected model
- persist benchmark runs under a per-job history layout instead of one mutable `bench-job.json`
- add controlled Hugging Face benchmark suites with explicit dataset provenance and queue metadata
- update the roadmap execution index and progress log to mark M7 completed once the real runner and evidence land

### 6. Benchmark CLI And CSV Export Closure

- add a shared benchmark export bundle decoder in `MelixControlPlaneCore` so Window UI and `melix` CLI render the same persisted benchmark history
- extend the shared control-plane client with `ops.export_results`
- expose `melix bench run`, `melix bench list`, and `melix bench export-csv`

### 7. Benchmark Window UI Visualization Closure

- add Window UI controls for model selection, suite multi-select, sample-size, batch-factor, history inspection, and result visualization
- wire Window UI history rendering and CSV export through the shared benchmark export bundle parser instead of bespoke decoding

### 8. Verification, Metrics, And Runbook Closure

- update runbooks, README CLI guidance, and productization verification steps
- record touched-scope Swift and Python changed-line coverage for each executable slice
- run `make proto`, `make py-test`, `make swift-test`, and `make integration-test` before final completion

## Verification

- documentation-only slices: explicit `N/A` coverage entry with reason
- Swift shared-client and CLI slices:
  - targeted `ControlPlaneXPCClientTests`
  - targeted CLI parser and execution tests
  - Swift changed-line coverage for touched control-plane and CLI files
- LoRA backend slices:
  - targeted `services/mlx-worker-python/tests/test_lora_model_ops.py`
  - targeted `services/mlx-worker-python/tests/test_maintenance_service.py`
  - Python changed-line coverage for touched worker files
- benchmark slices:
  - targeted `services/mlx-worker-python/tests/test_benchmark_schemas.py`
  - targeted benchmark export and maintenance tests
  - targeted `ControlPlaneServiceTests`, `RuntimeViewModelTests`, and `DesktopFoundationViewTests`
  - Swift and Python changed-line coverage for touched source

## Acceptance

- the active repository tracking reflects the real execution transaction
- `melix` CLI exposes LoRA training, LoRA activation, benchmark execution, benchmark listing, and benchmark CSV export
- Window UI and CLI both use shared control-plane truth
- LoRA can train from either a local package or a Hugging Face dataset configuration and can activate the resulting adapter into a derived model
- benchmark results come from real execution, persist per run, can be exported as CSV, and render in the Window UI with model and suite selection, history inspection, visualization, and CSV export
- M7 is only marked completed after the real benchmark runner and benchmark evidence are committed

## Assumptions And Constraints

- the operator surface remains the existing macOS window rather than a new standalone window family
- controlled benchmark suites remain repository-owned rather than arbitrary user-entered Hugging Face datasets
- the CLI is a same-host operator tool and does not implicitly start services in v1
- broader unrelated workspace compile drift may still require targeted verification to be the primary proof during intermediate commits
