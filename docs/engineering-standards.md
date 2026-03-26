# Melix Engineering Standards

This document defines the default engineering workflow for Melix.

## Purpose

Melix is being built as an executable local AI runtime, not just a document set or a schema dump. The repository must stay understandable to both humans and agents, and every meaningful change must leave behind evidence that the system is still coherent.

## Working Principles

- Treat docs as the system of record for architecture, protocols, and planned execution.
- Optimize for agent legibility as well as human readability.
- Prefer small, verifiable slices over broad refactors.
- Encode standards into commands, templates, and tests instead of relying on memory.
- Treat entropy management as first-class engineering work.

## Default Workflow

1. Read the relevant specs, standards, and the active plan before changing behavior.
2. Confirm the approach in plan mode before editing code. If plan mode is unavailable, create or update an explicit written plan first.
3. For non-trivial work, create or update a plan in `docs/plans/`.
4. Define the performance probes, measurement points, and success metrics for the affected path before implementation.
5. Implement in small slices with explicit boundaries.
6. Update docs, generated artifacts, and tests in the same change when behavior changes.
7. Run verification before claiming completion.

## Boundary Rules

The repository must preserve these ownership boundaries:

- `packages/protocol/schema` defines authoritative interfaces.
- `packages/protocol/swift` and `packages/protocol/python` contain generated outputs only.
- local JavaScript or TypeScript package operations use Bun by default
- the Swift control plane owns orchestration state, admission, external API translation, and operator-facing state
- the Python worker owns runtime execution state, streaming inference, and model-local runtime behavior
- the menu bar app is an operator shell, not a second control plane

Do not collapse those layers for convenience without an explicit architecture decision.

## Documentation Rules

- Formal docs are written in English.
- Discussion with the user stays in Chinese unless asked otherwise.
- Formal docs, examples, and identifiers use Melix naming only.
- Keep the current top-level canonical specs in place unless a migration task explicitly changes the docs layout.
- `docs/product-brief.md` remains intentionally ignored and untracked unless that policy is explicitly changed.

## Review Standard

Code review and self-review should prioritize:

- correctness and behavioral regressions
- boundary violations between protocol, control plane, worker, and UI surfaces
- missing or weak verification
- undocumented changes to externally visible behavior
- drift between schemas, generated outputs, and implementation code

Findings should be concrete and evidence-based.

## Testing and Verification Standard

- New behavior requires tests when practical.
- Interface or protocol changes require regenerated artifacts in the same change.
- No HTTP or API surface work is considered complete without corresponding tests and doc updates.
- Before any commit, measured automated test coverage for the repository scope touched by the change must be at least 95 percent.
- If coverage is not currently measurable for that scope, add or update the coverage command before committing.
- Design work must identify the performance probes needed to measure the affected path.
- Metrics collection points should be chosen early enough that performance regressions are detectable before merge.
- Before any commit or handoff, include a metrics report for the changed scope. If the change is documentation-only or the path is not yet measurable, include an explicit `N/A` metrics report with the reason.
- Verification commands must be reported with their outcomes.
- If a command cannot be run, say so explicitly and state why.

Recommended baseline commands:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

## Lockfile and Dependency Standard

- Commit `uv.lock`.
- Reproduce Python environments with `uv sync --frozen`.
- Commit `Package.resolved` for executable Swift workspaces when it exists.
- Do not refresh lockfiles casually in unrelated changes.
- If dependencies change, update the lockfiles in the same change.

## Generated Code Standard

- Do not hand-edit generated protobuf outputs.
- Regenerate generated code immediately after schema changes.
- Review generated diffs for correctness, but treat the schema as the editable source.

## Change Hygiene

Each substantial change should leave the repository in a coherent state:

- docs reflect the implemented behavior
- tests cover the behavior that changed
- generated outputs match the current schemas
- lockfiles match the declared dependency set
- dead scaffolding and stale references are removed when they would mislead future work

## Execution Evidence Checklist

Before calling work complete, capture evidence for the relevant slice:

- the plan or spec that governed the work
- the files or modules changed
- the defined performance probes and target metrics for the affected path
- the verification commands run
- the outcome of each verification command
- the metrics report or the explicit reason it is `N/A`
- any known gaps, deferred work, or unrun checks
