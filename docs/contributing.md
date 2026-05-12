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

---

## Coverage & Metrics

For any change that touches executable code:

- Automated coverage for the changed scope must be at least **95%**.
- If coverage is not measurable for that scope, record the reason explicitly in the PR.
- Include a metrics report for the changed scope.

For documentation-only changes, an explicit `N/A` metrics report is acceptable.

---

## Observability Changes

Choose the observability plane deliberately:

- Runtime metrics are for production health and should reuse counters already produced by request execution.
- Evidence-mode probes are for benchmark, evaluation, comparison, and release claims, and must preserve `run-evidence.json`, `probe_timeline`, and `telemetry_summary`.
- Debug diagnostics are opt-in local artifacts and must stay bounded; they do not qualify as public performance evidence.
- PR-scoped performance probes belong in `infra/perf/pr_scoped_probes.json` plus a focused script under `scripts/` when the workload is synthetic, repeated, base-vs-head, or uses monkeypatching/tracemalloc.

When adding a PR-scoped performance probe, follow the existing `probe-policy-noop-overhead` entry as the minimal pattern: declare `watch_globs`, `test_command`, `coverage_command`, `probe_command`, `probe_impl`, and machine-readable metrics. Keep synthetic probe scripts out of production package manifests.

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
