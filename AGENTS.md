# Melix Agent Entry Point

This file is the canonical starting point for agents working in this repository.

## Repository Purpose

Melix is a local-first AI runtime for Apple Silicon.

The current implementation slice focuses on:

- shared protobuf schemas and generated protocol artifacts
- a Swift control plane workspace
- a Python worker workspace
- a minimal macOS menu bar workspace

## Document Precedence

Use repository documents in this order:

1. `AGENTS.md`
2. canonical specifications under `docs/`
3. execution plans under `docs/plans/`
4. implementation code and tests

When a task changes behavior, update the relevant spec or plan together with the code.

## Language and Naming Rules

- Discuss work in Chinese unless the user asks otherwise.
- Write formal repository documents in English.
- Use Melix naming in formal docs, examples, bundle identifiers, and paths.
- Do not mention the reference products from `pre-docs` in formal docs.

## Command Contract

Use these commands as the default local workflow:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

For local JavaScript or TypeScript package operations, prefer Bun and `bunx`.

## Local Multi-Worktree Runtime Rules

Agents may work from multiple Melix worktrees on the same MacBook Pro. Code,
build products, and repository-local caches are worktree-scoped, but running
Melix stacks can still interfere through shared ports, process metadata, and
operator state. When starting a local Melix development stack from any worktree,
use a named instance, an explicit HTTP port, a worktree-local runtime directory,
and a worktree-local `MELIX_HOME`.

Do not run a bare `bash scripts/dev_up.sh` when another Melix worktree may be
running or when the task expects a long-lived local stack. Each concurrently
running worktree must use a different `MELIX_HTTP_PORT`. The bare
`scripts/dev_up.sh` default HTTP port is `12436`; named instances should use
different explicit ports, for example `12434` and `12435`.

Use this shell helper pattern for starting a development instance:

```bash
melix-dev-instance() {
  local instance_name="${1:-}"
  local http_port="${2:-}"

  if [[ -z "${instance_name}" || -z "${http_port}" ]]; then
    printf 'usage: melix-dev-instance <instance-name> <http-port>\n' >&2
    return 2
  fi

  if ! [[ "${http_port}" =~ ^[1-9][0-9]*$ ]] || (( http_port < 1024 || http_port > 65535 )); then
    printf 'http-port must be a number between 1024 and 65535\n' >&2
    return 2
  fi

  if [[ "${instance_name}" == *[^A-Za-z0-9_-]* ]]; then
    printf 'instance-name may only contain letters, numbers, underscores, and hyphens\n' >&2
    return 2
  fi

  local repo_root
  local runtime_dir
  local melix_home
  if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    printf 'fatal: not inside a git worktree\n' >&2
    return 1
  fi
  runtime_dir="${repo_root}/.runtime/sidecars/${instance_name}"
  melix_home="${repo_root}/.runtime/home-${instance_name}"

  export MELIX_SERVICE_INSTANCE_NAME="${instance_name}"
  export MELIX_HTTP_PORT="${http_port}"
  export MELIX_RUNTIME_DIR="${runtime_dir}"
  export MELIX_HOME="${melix_home}"

  bash "${repo_root}/scripts/dev_up.sh"
}
```

Use the matching runtime directory when stopping that instance:

```bash
melix-dev-stop-instance() {
  local instance_name="${1:-}"

  if [[ -z "${instance_name}" ]]; then
    printf 'usage: melix-dev-stop-instance <instance-name>\n' >&2
    return 2
  fi

  if [[ "${instance_name}" == *[^A-Za-z0-9_-]* ]]; then
    printf 'instance-name may only contain letters, numbers, underscores, and hyphens\n' >&2
    return 2
  fi

  local repo_root
  if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    printf 'fatal: not inside a git worktree\n' >&2
    return 1
  fi

  export MELIX_RUNTIME_DIR="${repo_root}/.runtime/sidecars/${instance_name}"

  bash "${repo_root}/scripts/dev_down.sh"
}
```

The stop helper only exports `MELIX_RUNTIME_DIR` because `scripts/dev_down.sh`
stops processes by pid files and runtime artifacts under that directory; it does
not use `MELIX_HTTP_PORT` or `MELIX_HOME`.

Example concurrent worktree ports:

```bash
melix-dev-instance wt-main 12434
melix-dev-instance wt-lora 12435
```

Stopping a named instance must use the same instance name:

```bash
melix-dev-stop-instance wt-main
```

If CLI or menu bar persisted state must be isolated, keep `MELIX_HOME`
worktree-local as shown above. The start helper exports `MELIX_HOME` in the
current shell session so later CLI commands use the same isolated state. Do not
share the default `~/.melix` state across parallel worktrees unless shared
operator state is intentional.

The repository-local `.runtime` tree is ignored by git. Never stage or commit
runtime pid files, sockets, logs, managed models, or worktree-local Melix home
state from `.runtime`.

## Source of Truth Rules

- Protobuf schemas under `packages/protocol/schema` are the authoritative interface definitions.
- Generated artifacts under `packages/protocol/swift` and `packages/protocol/python` are versioned outputs.
- Do not hand-edit generated protobuf outputs. Regenerate them after schema changes.
- Local JavaScript or TypeScript package operations should prefer Bun.
- The Swift control plane owns orchestration truth.
- The Python worker owns execution truth.

## Lockfile and Generated Artifact Policy

- Commit `uv.lock`.
- Use `uv sync --frozen` when reproducing the locked Python environment.
- Commit `Package.resolved` for executable Swift workspaces when it exists.
- If a change updates dependencies or protobuf schemas, include the regenerated lockfiles or generated outputs in the same change.

## Planning and Verification Rules

- Before each work transaction, read the relevant docs and standards before changing code.
- Confirm the implementation approach in plan mode before editing code. If plan mode is unavailable, create or update an explicit written plan before broad implementation.
- For non-trivial work, start from an explicit plan under `docs/plans/` or update the active plan before broad implementation.
- During design and solution evaluation, start from the best end-state architecture
  for Melix as if time and implementation cost were not constraints. Do not
  optimize the recommended direction for the shortest path, smallest diff, or
  lowest-effort patch. After the best solution is identified, slice the delivery
  into small, verifiable implementation steps.
- During design, define the performance probes, measurement points, and success metrics for the code path being changed.
- For material UI/UX changes, use the interactive walkthrough workflow in `docs/runbooks/agent-ui-walkthrough.md` before broad App implementation when feasible: create or update a `.runtime/walkthrough/` HTML artifact, review it with the operator in the in-app browser, record decisions in a paired runtime note, then implement after the direction is confirmed.
- Prefer small, verifiable slices over broad speculative rewrites.
- Do not claim completion without running the relevant verification commands and reporting the result.
- Before any commit, ensure measured automated test coverage for the repository scope touched by the change is at least 95 percent. If coverage is not currently measurable for that scope, add or update the coverage command before committing.
- Before any commit or handoff, include a metrics report for the changed scope. If the change is documentation-only or the path is not yet measurable, include an explicit `N/A` metrics report with the reason.
- Before committing on a macOS host with at least 128 GiB of physical memory, the versioned pre-commit hook under `.githooks/pre-commit` must run the full local test gate (`make swift-test`, `make py-test`, and `make integration-test`) and build the scoped performance report. Install the hook with `make git-hooks-install`; `make bootstrap` also installs it.
- The versioned pre-commit hook must use the repository-local `.uv-cache` and defaults to Python 3.12 for dependency compatibility. Set `MELIX_PRE_COMMIT_UV_PYTHON` only when a different supported interpreter is required for a local diagnosis.
- If the pre-commit performance report shows a regression, analyze the report before proceeding. If the regression is an intentional and acceptable tradeoff, commit only with `MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1` and a non-empty `MELIX_PRE_COMMIT_PERF_REGRESSION_REASON`, then record that rationale in the PR or handoff. Otherwise, fix the regression and rerun the hook before committing.

## Task Worktree and Pull Request Lifecycle Rules

- Start every new task from a fresh worktree created from the current
  `origin/main`. Fetch `origin/main` first, choose a task-specific branch name,
  and avoid mixing task work into a dirty checkout or an older branch.
- For multi-step tasks, create one focused commit for each completed step. Keep
  commits small enough that each commit maps to a reviewable task phase and has
  its own relevant verification or explicit `N/A` metrics note.
- Keep the task branch current with `origin/main` throughout the task. Merge
  `origin/main` promptly at natural boundaries and before creating or updating a
  pull request. When `origin/main` changes while a PR is under observation,
  merge it again before concluding the PR is ready.
- After opening or updating a pull request, continue monitoring the PR until it
  reaches a terminal outcome. Check code review, merge conflicts, CI status, and
  the PR performance report comment instead of relying on a single status signal.
- When code review appears, decide whether each comment requires a code or
  documentation change. Reply to the review thread either way: explain the fix
  made, or explain why no change is appropriate.
- When conflicts appear, resolve the textual conflicts and also inspect the new
  `origin/main` changes that caused or surround the conflict. Decide whether
  those newly introduced behaviors should be covered, replaced, or adapted by
  the current task, then re-verify the branch locally before pushing the
  resolution.
- When CI fails, treat the failing jobs as blockers. Inspect the logs, repair the
  branch, rerun the relevant local verification when feasible, and push the fix.
- When the performance report identifies a regression, treat it as a blocker
  unless the report or direct probe artifacts prove it is outside the PR scope.
  Fix in-scope regressions and document non-blocking findings in the PR.
- Squash merge only after code review threads are resolved, any required reviewer
  approval is present, conflicts are resolved, CI is green, the performance
  report is acceptable, PR evidence is complete, and the branch is current with
  `origin/main`.

## Pull Request Evidence Rules

Before creating or updating a pull request, read and follow:

1. `.github/pull_request_template.md`
2. `docs/contributing.md`
3. `docs/templates/pr-evidence-checklist.md`

The pull request body must keep the template section headings exactly,
including `## Plan or Spec`, `## Commands Run`, `## Coverage and Metrics`,
and `## Known Gaps`. The `pr-evidence` GitHub Actions workflow validates these
headings through `scripts/validate_pr_evidence.py`; do not open a pull request,
including a draft pull request, with an empty body, placeholder body, or a body
that omits those sections.

For behavior changes, identify a governing canonical spec or plan from `docs/`
or `docs/plans/`. If no such document applies, write `N/A: <reason>` in the
`Plan or Spec` section and explain why the change is intentionally not governed
by a canonical plan or spec. Session-local notes outside the repository do not
replace the required PR evidence.

## Documentation Rules

- `docs/product-brief.md` remains intentionally ignored and untracked unless the user explicitly changes that policy.
- Keep canonical top-level specs in place unless there is an explicit reorganization task.
- New architecture, decision, and runbook material should use the structure documented in `docs/README.md`.
