# Task Plan

## Goal

Close the remaining M7 gaps on `main`, make LoRA product-ready across Window UI and CLI, and then finish Benchmark productization with real execution, controlled Hugging Face suites, visualization, and CSV export.

## Scope

- refresh progress and execution documents so M7, LoRA, Benchmark, and CLI work are tracked from the current repository state
- expose a shared local control-plane client surface so Window UI and `melix` CLI can reuse the same operator commands
- productize LoRA training and activation with local-package and Hugging Face dataset inputs, stable artifact storage, Window UI forms, and CLI commands
- complete M7 with real benchmark execution, per-run persistence, controlled Hugging Face benchmark suites, and executable evidence
- productize Benchmark with Window UI model and suite selection, history views, visualization, and CSV export

## Phases

1. Documentation reset and execution baseline
   - status: completed
2. Shared operator client and CLI foundation
   - status: completed
3. LoRA backend and artifact productization
   - status: completed
4. LoRA Window UI and CLI exposure
   - status: completed
5. Real benchmark runner and M7 closure
   - status: completed
6. Benchmark CLI and CSV export closure
   - status: completed
7. Benchmark Window UI visualization closure
   - status: completed
8. Final verification, metrics, and progress closure
   - status: pending

## Acceptance

- Progress and roadmap documents describe the true M7 and productization state and point at the active execution plan.
- LoRA training accepts either a local dataset package or a Hugging Face dataset configuration, persists reproducible artifacts under the runtime jobs root, and exposes training plus activation through Window UI and `melix` CLI.
- Activated adapters register derived text models that can be selected for inference through the existing product shell.
- Benchmark executes real measurements against an explicitly selected model, persists per-run results, supports controlled Hugging Face suites with on-demand caching, and can export CSV.
- Window UI and CLI both operate through the control-plane truth rather than bypassing it.
- Touched Python and Swift scope maintain measured changed-line coverage of at least `95%` where executable lines exist.

## Risks

- Swift package verification may remain slower than the Python worker path because of large workspace recompilation.
- Real benchmark execution depends on loaded text-model availability and runtime characteristics that differ between deterministic and MLX-backed environments.
- Hugging Face dataset materialization must remain testable without network access, so loader seams need explicit fixture-driven coverage.

## Outcome

- Completed slices:
  - documentation reset and execution baseline
  - shared operator client and CLI foundation
  - LoRA backend and artifact productization
  - LoRA Window UI and CLI exposure
  - benchmark core runner, per-run persistence, and export compatibility
  - controlled Hugging Face benchmark suites and M7 closure
  - benchmark CLI listing and CSV export closure
  - benchmark Window UI visualization closure
- Remaining slices:
  - final verification, metrics, and progress closure
