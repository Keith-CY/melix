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
running worktree must use a different `MELIX_HTTP_PORT`.

Use this shell helper pattern for starting a development instance:

```bash
melix-dev-instance() {
  local instance_name="${1:-}"
  local http_port="${2:-}"

  if [[ -z "${instance_name}" || -z "${http_port}" ]]; then
    printf 'usage: melix-dev-instance <instance-name> <http-port>\n' >&2
    return 2
  fi

  if [[ "${instance_name}" == *[^A-Za-z0-9_-]* ]]; then
    printf 'instance-name may only contain letters, numbers, underscores, and hyphens\n' >&2
    return 2
  fi

  local repo_root
  local runtime_dir
  local melix_home
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
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
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

  export MELIX_RUNTIME_DIR="${repo_root}/.runtime/sidecars/${instance_name}"

  bash "${repo_root}/scripts/dev_down.sh"
}
```

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
- During design, do not anchor on minimal change or implementation cost. Optimize for the best end-state architecture, best practices, and the most reasonable long-term choice for Melix.
- During design, define the performance probes, measurement points, and success metrics for the code path being changed.
- Prefer small, verifiable slices over broad speculative rewrites.
- Do not claim completion without running the relevant verification commands and reporting the result.
- Before any commit, ensure measured automated test coverage for the repository scope touched by the change is at least 95 percent. If coverage is not currently measurable for that scope, add or update the coverage command before committing.
- Before any commit or handoff, include a metrics report for the changed scope. If the change is documentation-only or the path is not yet measurable, include an explicit `N/A` metrics report with the reason.

## Documentation Rules

- `docs/product-brief.md` remains intentionally ignored and untracked unless the user explicitly changes that policy.
- Keep canonical top-level specs in place unless there is an explicit reorganization task.
- New architecture, decision, and runbook material should use the structure documented in `docs/README.md`.
