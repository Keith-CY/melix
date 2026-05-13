# Contributing to Melix

Melix welcomes contributions of all kinds — documentation, tooling, protocol definitions, runtime improvements, CLI features, and macOS operator surface work. Every fix matters, and good documentation contributions are just as valued as code.

---

## Before You Start

Read these three documents before making a broad change:

1. [`AGENTS.md`](../AGENTS.md) — Repository-wide constraints and agent guidance
2. [`docs/README.md`](README.md) — The documentation map and precedence rules
3. [`docs/engineering-standards.md`](engineering-standards.md) — Coding, documentation, and tooling conventions

If your change affects behavior, update the relevant spec, runbook, or roadmap document in the same commit.

---

## Preferred Workflow

1. **Branch from `main`** in an isolated branch or worktree.
2. **Keep changes small** and focused on one behavior slice.
3. **Prefer one coherent change per PR** rather than mixing a refactor with a feature.
4. **Update the documentation** that should reflect the new behavior as part of the same change.

---

## Verification Commands

Run these commands before opening a PR. They are the baseline verification gate for the entire repository:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

GitHub Actions runs the same gates on every PR. If you are working in a specific subsystem, add any relevant focused commands, smoke scripts, or runbook verification steps to your PR description.

`make bootstrap` installs the repository git hooks by configuring `core.hooksPath=.githooks`. You can also run `make git-hooks-install` directly. On macOS hosts with at least 128 GiB of physical memory, the pre-commit hook runs the full local test gate and writes a scoped performance report under `.runtime/pre-commit-performance/`. The hook uses the repository-local `.uv-cache` and defaults `UV_PYTHON` to Python 3.12; set `MELIX_PRE_COMMIT_UV_PYTHON` when a different supported interpreter is required. A regression in that report blocks the commit unless it has been analyzed and is explicitly allowed with both `MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1` and `MELIX_PRE_COMMIT_PERF_REGRESSION_REASON`.

---

## Coverage & Metrics

For any change that touches executable code:

- Automated coverage for the changed scope must be at least **95%**.
- If coverage is not measurable for that scope, record the reason explicitly in the PR.
- Include a metrics report for the changed scope.

For documentation-only changes, an explicit `N/A` metrics report is acceptable.

---

## What Makes a Good PR

A clear and complete PR includes:

- **What changed and why** — a short narrative of the intent
- **Which commands were run** — paste the relevant `make` output or test results
- **Coverage and metrics** — or an explicit `N/A` with a reason
- **Evidence** — screenshots, JSON bundles, or smoke logs when UI or acceptance behavior changed

The [PR template](../.github/pull_request_template.md) captures these expectations. Fill it out fully — reviewers rely on it.

---

## Documentation Rules

- Write all formal repository documents in English.
- Keep the root `README.md` focused on what Melix is, why it exists, who it is for, and how to get started.
- Put onboarding and guide material under `docs/`.
- Put executable operating procedures under `docs/runbooks/`.
- Keep canonical top-level specs in place unless there is an explicit migration task.

---

## Tooling Conventions

- Use **Bun** for local JavaScript or TypeScript package operations.
- Do **not** hand-edit generated protobuf outputs — regenerate them from `packages/protocol/schema` using `make proto`.
- Commit `uv.lock` and generated outputs when dependency or schema changes require them.

---

## Useful References

- [Current Status](current-status.md) — What's shipped and where the limits are
- [Runbook Index](runbooks/README.md) — All operator runbooks
- [PR Evidence Checklist](templates/pr-evidence-checklist.md) — Quick-reference checklist for PR completeness
