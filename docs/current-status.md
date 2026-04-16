# Melix Current Status

Date: 2026-04-12

## Summary

Melix is currently a local Apple Silicon runtime product centered on model operations, server
session control, CLI plus macOS operator workflows, LoRA training, and benchmark or evaluation
loops. The repository is no longer just a Phase 0 thin path; the active product slice has already
closed the original Phase 8 productization scope for this codebase.

## Shipped Today

- local model registry management, including multi-root discovery, local import, and Hub-backed download flows
- server session lifecycle workflows, including create, update, select, start, pause, resume, wake, and stop
- local chat and operator workflows through the public `melix` CLI
- LoRA and QLoRA training, adapter activation, derived-model lifecycle, and compare-ready outputs
- benchmark, matrix benchmark, evaluation, compare, and export flows from shared product-owned surfaces
- a native macOS operator surface backed by the same CLI-first workflow authority used by the shipped product
- packaging and install paths for launch agents, Homebrew service use, and preview app-bundle delivery

## Current Operator Surfaces

- the public `melix` CLI
- the native macOS menubar and operator workspace
- the local control-plane API and compatibility surfaces documented in the protocol and onboarding docs

## Verified Product Flows

The repository currently records product-level evidence for:

- deterministic LoRA CLI and Window UI acceptance smokes
- Phase 8 CLI acceptance bundle capture
- Phase 8 native Window UI acceptance bundle and screenshot capture
- release-gate automation through the repository-owned Phase 8 release gate and GitHub workflow

The repository-wide default verification contract remains centered on `make proto`,
`make py-test`, `make swift-test`, and `make integration-test`, but current local caveats should
always be checked against the latest `progress.md` entry before treating that full gate as clean.

The most detailed acceptance evidence summary is tracked in:

- [`progress.md`](../progress.md)
- [`docs/runbooks/phase-8-product-acceptance.md`](runbooks/phase-8-product-acceptance.md)
- [`docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`](plans/2026-03-30-full-capability-roadmap-execution-index.md)

The current forward-looking LoRA expansion breakdown is tracked in:

- [`docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`](plans/2026-04-16-lora-capability-modules-and-commit-plan.md)

## Honest Boundaries

- Melix is intentionally scoped to macOS on Apple Silicon.
- The current docs should be read as productized local-runtime documentation, not as a promise of cross-platform support.
- Disk-streaming remains an evidence-only boundary today. The repository documents the probes and unsupported-path evidence, but true SSD-backed runtime execution is still not shipped.
- The historical plan archive is broader than the curated product docs. Use the execution index as an engineering record, not as shorthand for every archived plan being equally product-ready.
- `progress.md` still tracks active repository-level verification notes. If you are working inside the repo, treat the latest progress log as the operational truth for known local issues.

## Best Entry Points

- use [`docs/getting-started.md`](getting-started.md) for the fastest setup path
- use [`docs/phase-roadmap.md`](phase-roadmap.md) for the original phase model and its current closure status
- use [`docs/runbooks/benchmark-matrix-evaluation-and-lora.md`](runbooks/benchmark-matrix-evaluation-and-lora.md) for the benchmark and evaluation operator flow
- use [`docs/runbooks/phase-8-local-install.md`](runbooks/phase-8-local-install.md) for product-style local installs
- use [`docs/README.md`](README.md) for the broader documentation map
