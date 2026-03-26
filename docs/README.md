# Melix Documentation Map

This directory is the system of record for Melix product, architecture, protocol, and execution guidance.

## Precedence

Use documents in this order when resolving ambiguity:

1. `../AGENTS.md`
2. canonical specifications in this directory
3. execution plans in `docs/plans/`
4. templates in `docs/templates/`

## Canonical Specifications

The current top-level specifications remain canonical and should not be moved without an explicit migration task:

- `architecture-spec.md`
- `control-plane-protocol.md`
- `worker-rpc-schema.md`
- `repo-skeleton.md`

## Planning

Plans live under `docs/plans/`.

Use a plan for non-trivial changes that touch multiple modules, change architecture boundaries, or require staged verification.

Current active implementation plan:

- `plans/2026-03-27-phase-0-thin-path.md`

## Engineering Standards

Repository-wide engineering rules are defined in:

- `engineering-standards.md`

Use that document for workflow, verification, review, and change-boundary rules.

## Forward Structure

The repository will organize future documents under these paths without moving the current canonical specifications yet:

- `architecture/` for module-level design notes and subsystem breakdowns
- `decisions/` for decision records and irreversible tradeoffs
- `runbooks/` for startup, debugging, and recovery procedures
- `templates/` for reusable planning, architecture, and operations templates

## Operating Constraints

- Formal docs in this repository are written in English.
- Melix naming is the only naming used in formal docs and examples.
- Protocol schemas under `packages/protocol/schema` are the authoritative interface definitions.
- Generated protocol outputs are committed artifacts and must be regenerated when schemas change.
