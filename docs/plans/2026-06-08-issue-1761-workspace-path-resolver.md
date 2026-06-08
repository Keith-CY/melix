# Issue 1761 Workspace Path Resolver Plan

## Goal

Introduce a shared Python worker workspace path resolver so future agent and
local-job read/write/edit tools have a concrete workspace-root boundary before
they mutate or inspect filesystem paths.

## Scope

This slice covers the reusable boundary only:

- resolve relative paths inside an active workspace root
- accept absolute paths only when they resolve inside that root
- reject `..` traversal and symlink escapes after realpath normalization
- reject sensitive filenames inside the workspace
- return machine-readable receipt details for allowed and blocked paths
- document the boundary in the unified agentic tool runtime contract

This slice does not add a new read/write/edit tool and does not retrofit all
existing local-job pipelines. Those remain follow-up work under #1761 once the
shared resolver exists.

## Architecture

The end-state architecture is a single resolver that agent tools, local-job
operators, and workflow actions can call before any filesystem mutation or
workspace read. The resolver returns a value object with `workspace_root`,
`requested_path`, `resolved_path`, `allowed`, and `refusal_reason`, making
receipts deterministic without forcing each caller to duplicate containment
logic.

This slice keeps the implementation in
`worker.runtime.workspace_paths` because it is runtime safety infrastructure,
not workspace-manifest schema validation. Workspace manifest preflight keeps its
existing relative-path schema checks; this resolver handles live path requests
and symlink-aware containment.

## Performance Probes And Metrics

The resolver runs only when a workspace path is requested. The hot path is one
`Path.resolve(strict=False)` call for the workspace root and requested path plus
a filename sensitivity check. There is no registered PR-scoped performance
probe expected for this change; the PR-scoped performance report must still
show `Status: ok`, regressions `0`, and verification failures `0`.

Verification will include:

- focused pytest for the resolver
- changed-line coverage for the resolver and tests with a target of at least
  95 percent
- local PR-scoped performance report with `Status: ok`

## Implementation Steps

1. Add failing tests in
   `services/mlx-worker-python/tests/test_workspace_path_resolver.py` for:
   - relative in-workspace paths
   - absolute in-workspace paths
   - `..` traversal escapes
   - symlink escapes
   - sensitive filenames such as `.env`
2. Implement `WorkspacePathResolver` and `WorkspacePathResolution` in
   `services/mlx-worker-python/worker/runtime/workspace_paths.py`.
3. Add `receipt_fields()` so callers can attach resolver evidence to local-job
   and tool receipts.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to make this resolver
   the required boundary for future workspace path tools.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates
   before opening the PR.

## Success Criteria

- Relative and absolute paths inside the workspace resolve as allowed.
- Traversal and symlink escapes are blocked before callers can use the target.
- Sensitive filenames remain blocked even inside the workspace.
- Resolver receipts include `workspace_root`, `requested_path`,
  `resolved_path`, `allowed`, and `refusal_reason`.
- Contract docs identify this as the first shared workspace-path boundary under
  #1761, with read/write/edit tool integration left for later slices.
