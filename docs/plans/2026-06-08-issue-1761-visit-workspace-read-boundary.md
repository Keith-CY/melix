# Issue 1761 Visit Workspace Read Boundary Plan

## Goal

Wire the existing workspace path resolver into the deterministic `visit` tool
for local workspace file reads.

## Scope

This slice covers the Python worker deterministic agentic tool runtime:

- `visit` tool calls whose URL is a local filesystem path or `file://` URI
- explicit `fixture_context.workspace_root` opt-in for local file reads
- workspace resolver receipts attached to `visit` observations
- fail-closed behavior for traversal, symlink escapes, and sensitive filenames
- the governing unified agentic tool runtime contract

This slice does not add new read, write, or edit tools. It also does not
retrofit generic RAG stores, skill entrypoints, memory entrypoints, or
background-job continuations.

## Architecture

The `WorkspacePathResolver` is already the shared containment and sensitive
filename primitive. This slice makes `visit` the first concrete built-in tool
consumer. The runtime should only read a local file when
`fixture_context.workspace_root` is a configured string and the requested
`visit.url` is a relative path, absolute path, or `file://` URI that resolves
inside that workspace root.

Resolver failures must become failed tool observations before any filesystem
read. Successful reads return a normal `page_extract` payload with a
`workspace_path_receipt` so downstream prompt or run evidence can prove the
read crossed the workspace boundary deliberately.

## Performance Probes And Metrics

The path adds one resolver call and one small text file read only when an
operator explicitly configures a workspace root and invokes `visit` against a
local path. Existing fixture-backed `visit` calls remain unchanged. No
registered PR-scoped probe is expected for this exact runtime helper, but the
PR-scoped performance report must still show status `ok`, regressions `0`, and
verification failures `0`.

Verification will include:

- focused pytest for local file `visit` success and refusal receipts
- full `services/mlx-worker-python/tests/test_agentic_tools.py`
- changed-line coverage for modified Python files with a target of at least
  95 percent
- local PR-scoped performance report with status `ok`

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`
   for:
   - `visit` reading a workspace-local Markdown file through a `file://` URI
   - `visit` refusing parent traversal before reading
   - `visit` refusing sensitive filenames inside the workspace
2. Implement local path parsing and workspace resolver use in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
3. Add a failed-observation helper for workspace path refusals that includes
   `reason = workspace_path_refused` and the resolver receipt fields.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to record `visit` as
   the first concrete workspace-read consumer and describe the receipt payload.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates
   before opening the PR.

## Success Criteria

- `visit` can read a local text file only when `fixture_context.workspace_root`
  is configured and the requested path resolves inside that workspace root.
- Refused workspace paths produce failed observations with
  `workspace_path_refused` and `workspace_path_receipt` evidence.
- Sensitive filenames remain blocked even inside the workspace.
- Existing fixture-backed `visit` behavior remains unchanged.
- Contract docs identify this as the first concrete workspace-read integration
  under #1761, with write/edit and broader prompt-context surfaces left for
  later slices.
