# Melix Documentation

Welcome to the Melix documentation. This is the central reference for everything about the product — from first-time setup to deep protocol specifications.

---

## Start Here

If you're new to Melix, begin with these three documents in order:

1. **[Getting Started](getting-started.md)** — Bootstrap the repo, start the local stack, and run your first CLI commands.
2. **[Current Status](current-status.md)** — Understand what is shipped today, what works, and where the honest boundaries are.
3. **[Phase Roadmap](phase-roadmap.md)** — See the original phase model and the current completion state.

---

## Guides & How-Tos

Practical guides for common tasks:

| Guide | What It Covers |
|---|---|
| [Getting Started](getting-started.md) | Fresh-checkout setup, first CLI flows, and the local stack |
| [Contributing](contributing.md) | Workflow, verification commands, PR expectations, and coverage rules |
| [Engineering Standards](engineering-standards.md) | Repository-wide coding, documentation, and tooling conventions |
| [Marketing And Storytelling Kit](marketing/README.md) | Product overview, LoRA narrative, reusable copy, and screenshot evidence |

---

## Runbooks

Step-by-step operating procedures for specific workflows. Use these when you need executable instructions rather than narrative explanation.

| Runbook | What It Covers |
|---|---|
| [Agent UI Walkthrough](runbooks/agent-ui-walkthrough.md) | Browser-based walkthrough workflow for substantial UI/UX changes before App implementation |
| [Local Stack](runbooks/phase-1-local-stack.md) | Runtime layout, environment exports, and alternate startup modes |
| [Benchmark, Matrix & LoRA](runbooks/benchmark-matrix-evaluation-and-lora.md) | Full operator guide: benchmarking, matrix runs, evaluation, and LoRA fine-tuning |
| [LoRA Adapter Workflow](runbooks/phase-8-lora-adapter-workflow.md) | Training, activating, publishing, and removing LoRA adapters |
| [Local Install](runbooks/phase-8-local-install.md) | Install Melix as a persistent local service via launch agent |
| [Homebrew Install](runbooks/homebrew-install.md) | Install and manage Melix through Homebrew |
| [Packaging Targets](runbooks/platform-packaging-targets.md) | Launch agent, Homebrew service, and preview app-bundle delivery options |
| [Release Gates](runbooks/phase-8-release-gates.md) | Automated release gate workflow and verification criteria |
| [Product Acceptance](runbooks/phase-8-product-acceptance.md) | Acceptance evidence and product-level smoke procedures |
| [Structured Streaming](runbooks/structured-streaming-reasoning-continuity.md) | Streaming and reasoning continuity behavior |
| [Serving Diagnostics Evidence](runbooks/serving-diagnostics-evidence.md) | Serving diagnostics bundles and baseline-vs-accelerated evidence artifacts |
| [All Runbooks →](runbooks/README.md) | Full runbook index |

---

## Canonical Specifications

These are the authoritative interface and architecture definitions. Do not move or rename them without an explicit migration task.

| Specification | What It Defines |
|---|---|
| [Architecture Spec](architecture-spec.md) | System-wide architecture, component responsibilities, and runtime layout |
| [Control Plane Protocol](control-plane-protocol.md) | The typed protocol between the control plane and worker surfaces |
| [Worker RPC Schema](worker-rpc-schema.md) | RPC message shapes and worker communication contracts |
| [Benchmark & Evaluation Contract](benchmark-evaluation-contract.md) | Benchmark and evaluation data formats, output contracts, and artifact shapes |
| [Evidence, Telemetry & Report Contract](evidence-telemetry-report-contract.md) | Run evidence, probe timeline, Apple Silicon telemetry, report, and release-gate source-of-truth rules |
| [Repository Skeleton](repo-skeleton.md) | Directory layout and conventions for the Melix repository |

---

## Architecture & Decisions

Design rationale and architecture decision records:

- [Architecture Overview](architecture/README.md)
- [Server Session & Desktop Shell](architecture/2026-04-01-server-session-desktop-shell.md)
- [Service-First Sidecar Reuse](architecture/2026-04-02-service-first-sidecar-reuse.md)
- [TurboQuant KV Cache Optimization](architecture/2026-04-18-turboquant-kv-cache-optimization.md)
- [Decision Records](decisions/README.md)

---

## Reference Scans

External product and architecture scans that have been converted into Melix
follow-up work:

- [Sparrow and LocalAI Lessons](reference-scans/sparrow-localai-lessons.md)
  Reference scan for structured local task workflows, operator UX, and follow-up
  issue priority.

---

## Examples

- [`examples/pipelines/phase8-acceptance.pipeline.json`](examples/pipelines/phase8-acceptance.pipeline.json) — The v1 typed CLI pipeline format used in the Phase 8 acceptance flow.

---

## Historical Planning Archive

The plan archive is intentionally large and serves as an engineering record. Use the entry points below before diving into individual plan files.

| Entry Point | What It Contains |
|---|---|
| [Full Capability Execution Index](plans/2026-03-30-full-capability-roadmap-execution-index.md) | Milestone-level closure detail for the full capability roadmap |
| [Full Capability Roadmap](plans/2026-03-30-full-capability-roadmap.md) | The original full capability plan |
| [Evidence, Telemetry & Report Roadmap](plans/2026-05-08-evidence-telemetry-roadmap.md) | Best-path plan for structured run evidence, probes, Apple Silicon telemetry, reports, PR/release gates, and desktop operator surfaces |
| [README & Docs Realignment](plans/2026-04-12-readme-and-docs-realignment.md) | Documentation restructure and alignment plan |
| [LoRA Capability Modules](plans/2026-04-16-lora-capability-modules-and-commit-plan.md) | LoRA expansion breakdown and commit plan |

> **Note:** The historical plan archive reflects engineering exploration, not a promise that every archived plan is equally product-ready. Treat `current-status.md` and active runbooks as the operational truth.

---

## Document Precedence

When documents appear to conflict, resolve ambiguity in this order:

1. `../AGENTS.md`
2. Canonical specifications in `docs/`
3. Active runbooks and status documents in `docs/`
4. Historical execution plans in `docs/plans/`
5. Templates in `docs/templates/`

---

## Operating Constraints

- All formal documents in this repository are written in English.
- "Melix" is the only product name used in formal docs and examples.
- Protocol schemas under `packages/protocol/schema` are the authoritative interface definitions — do not hand-edit generated outputs.
- Generated protocol outputs are committed artifacts and must be regenerated when schemas change.
