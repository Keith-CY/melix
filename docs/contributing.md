# Contributing To Melix

Melix accepts documentation, tooling, protocol, runtime, CLI, and operator-surface contributions.

## Start Here

Before making a broad change, read:

1. `AGENTS.md`
2. [`docs/README.md`](README.md)
3. [`docs/engineering-standards.md`](engineering-standards.md)

If your change affects behavior, update the relevant spec, runbook, roadmap, or plan in the same
transaction.

## Preferred Workflow

1. Start from `main` in an isolated branch or worktree.
2. Keep the change small enough to verify and explain.
3. Prefer one coherent behavior slice per change rather than a mixed refactor.
4. When a behavior changes, update the documentation that should be the new source of truth.

## Default Verification Commands

Use these commands as the repository baseline unless the touched scope has a narrower targeted
gate:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

If you are working in a specific subsystem, add the relevant focused commands, smoke scripts, or
runbook verification steps to your handoff note as well.

## Coverage And Metrics Expectations

Before any commit or handoff involving executable code:

- measured automated coverage for the touched executable scope must be at least `95%`
- if changed-line coverage is not measurable for that scope, record the reason explicitly
- include a metrics report for the changed scope

For documentation-only changes, an explicit `N/A` metrics report is acceptable.

## Documentation Rules

- Formal repository documents are written in English.
- Keep the root `README.md` focused on what Melix is, why it exists, who it is for, and how to get started.
- Put onboarding material under `docs/`.
- Put executable operating procedures under `docs/runbooks/`.
- Keep canonical top-level specs in place unless there is an explicit migration task.

## Tooling Conventions

- Use Bun for local JavaScript or TypeScript package operations when such operations are needed.
- Do not hand-edit generated protobuf outputs; regenerate them from `packages/protocol/schema`.
- Commit `uv.lock` and relevant generated outputs when dependency or schema changes require them.

## Handoff Expectations

A good handoff or PR should include:

- what changed and why
- which commands were run
- coverage and metrics results, or an explicit `N/A`
- screenshots, JSON bundles, or smoke evidence when UI or acceptance behavior changed

## Useful References

- [`docs/current-status.md`](current-status.md)
- [`docs/runbooks/README.md`](runbooks/README.md)
- [`docs/templates/pr-evidence-checklist.md`](templates/pr-evidence-checklist.md)
