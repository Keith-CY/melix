# Melix Documentation Map

This directory is the system of record for Melix product, architecture, protocol, and execution
guidance.

## Precedence

Use documents in this order when resolving ambiguity:

1. `../AGENTS.md`
2. canonical specifications in `docs/`
3. active runbooks and status documents in `docs/`
4. historical execution plans in `docs/plans/`
5. templates in `docs/templates/`

## Product And Status

Start here if you need the current project story before the engineering archive:

- [`current-status.md`](current-status.md)
- [`getting-started.md`](getting-started.md)
- [`contributing.md`](contributing.md)
- [`phase-roadmap.md`](phase-roadmap.md)

## Operations And Runbooks

Use runbooks when you need executable procedures instead of narrative documentation:

- [`runbooks/README.md`](runbooks/README.md)
- [`runbooks/phase-1-local-stack.md`](runbooks/phase-1-local-stack.md)
- [`runbooks/benchmark-matrix-evaluation-and-lora.md`](runbooks/benchmark-matrix-evaluation-and-lora.md)
- [`runbooks/phase-8-lora-adapter-workflow.md`](runbooks/phase-8-lora-adapter-workflow.md)
- [`runbooks/phase-8-local-install.md`](runbooks/phase-8-local-install.md)
- [`runbooks/homebrew-install.md`](runbooks/homebrew-install.md)
- [`runbooks/platform-packaging-targets.md`](runbooks/platform-packaging-targets.md)
- [`runbooks/phase-8-release-gates.md`](runbooks/phase-8-release-gates.md)
- [`runbooks/phase-8-product-acceptance.md`](runbooks/phase-8-product-acceptance.md)

## Canonical Specifications

These top-level specs remain canonical and should not be moved without an explicit migration task:

- [`architecture-spec.md`](architecture-spec.md)
- [`benchmark-evaluation-contract.md`](benchmark-evaluation-contract.md)
- [`control-plane-protocol.md`](control-plane-protocol.md)
- [`worker-rpc-schema.md`](worker-rpc-schema.md)
- [`repo-skeleton.md`](repo-skeleton.md)

## Architecture And Decisions

- [`architecture/README.md`](architecture/README.md)
- [`architecture/2026-04-01-server-session-desktop-shell.md`](architecture/2026-04-01-server-session-desktop-shell.md)
- [`architecture/2026-04-02-service-first-sidecar-reuse.md`](architecture/2026-04-02-service-first-sidecar-reuse.md)
- [`decisions/README.md`](decisions/README.md)

## Historical Planning Archive

The plan tree is intentionally large. Use these entry points before diving into individual child
plans:

- [`plans/2026-03-30-full-capability-roadmap-execution-index.md`](plans/2026-03-30-full-capability-roadmap-execution-index.md)
- [`plans/2026-03-30-full-capability-roadmap.md`](plans/2026-03-30-full-capability-roadmap.md)
- [`plans/2026-04-12-readme-and-docs-realignment.md`](plans/2026-04-12-readme-and-docs-realignment.md)
- [`plans/2026-04-16-lora-capability-modules-and-commit-plan.md`](plans/2026-04-16-lora-capability-modules-and-commit-plan.md)

## Engineering Standards

Repository-wide engineering rules are defined in:

- [`engineering-standards.md`](engineering-standards.md)

## Operating Constraints

- Formal docs in this repository are written in English.
- Melix naming is the only naming used in formal docs and examples.
- Protocol schemas under `packages/protocol/schema` are the authoritative interface definitions.
- Generated protocol outputs are committed artifacts and must be regenerated when schemas change.
