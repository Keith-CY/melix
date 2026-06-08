# Issue 1761 Workspace File Tools Plan

## Goal

Add concrete Python worker workspace file read/write/edit operators that route
every requested path through `WorkspacePathResolver` before any filesystem read
or mutation.

## Scope

This slice covers a reusable runtime primitive for future agent, MCP, and
workflow file surfaces:

- read UTF-8 workspace files only after resolver admission
- write UTF-8 workspace files only after resolver admission
- edit UTF-8 workspace files by exact text replacement only after resolver
  admission
- return a machine-readable receipt for allowed and refused operations
- return `status = failed` receipts for admitted paths when filesystem or
  decoding errors occur instead of letting those exceptions escape the tool
  boundary
- prove refused paths do not reach the final read or mutation path
- document the concrete operator boundary in the unified agentic tool runtime
  contract

This slice does not expose new public MCP namespaces, change the Swift MCP
catalog, or connect these operators to a live model-request tool execution path.
Those surfaces can call this primitive once the executor surface is introduced.

## Architecture

The best end state is one workspace file operator layer shared by agentic tools,
workflow actions, and local-job mutation surfaces. The layer accepts an active
workspace root, delegates path containment and sensitive filename policy to the
existing `WorkspacePathResolver`, and then performs the requested file operation
only when `allowed = true`.

The operator lives in `worker.runtime.workspace_file_tools` because it is
runtime safety infrastructure, not productization schema validation. Receipts
reuse the resolver fields and add `schema_version`, `tool_name`, `status`,
byte counts, and edit replacement counts so future tool observations can attach
the decision without reconstructing filesystem state. Byte counters describe
completed tool effects only: failed receipts keep `bytes_read = 0` and
`bytes_written = 0` even when a preflight read happened before a replacement
count mismatch.

## Performance Probes And Metrics

The path boundary adds one resolver call per requested file operation. Allowed
reads/writes/edits already perform filesystem IO; blocked operations stop before
opening or mutating the target. There is no registered PR-scoped synthetic probe
expected for this new primitive. The PR-scoped performance report must still
show `Status: ok`, regressions `0`, and verification failures `0`.

Verification will include:

- focused pytest for the workspace file tools
- changed-line coverage for the new module and tests with a target of at least
  95 percent
- full local pre-commit gate before opening the PR
- remote PR performance report with no regressions

## Implementation Steps

1. Add failing tests in
   `services/mlx-worker-python/tests/test_workspace_file_tools.py` for:
   - allowed read/write/edit paths emitting resolver receipts
   - symlink escapes being refused before read/write/edit mutation
   - sensitive filenames being refused before parent-directory creation or file
     mutation
   - admitted missing-file and write parent errors returning failed receipts
2. Implement `WorkspaceFileTools` and `WorkspaceFileToolResult` in
   `services/mlx-worker-python/worker/runtime/workspace_file_tools.py`.
3. Update `docs/unified-agentic-tool-runtime-contract.md` so the workspace path
   boundary identifies this file-tool primitive as the first concrete
   read/write/edit implementation under #1761.
4. Run focused tests, changed-scope coverage, `git diff --check`, commit, run
   the full pre-commit gate, open the PR, and monitor CI plus performance.

## Success Criteria

- Every read/write/edit method calls `WorkspacePathResolver.resolve()` before
  any file open, write, parent-directory creation, or edit mutation.
- Traversal, symlink escapes, and sensitive filenames produce `status = failed`
  receipts with resolver refusal reasons.
- Refused write/edit calls leave outside files and sensitive-path parent
  directories unchanged.
- Filesystem and text decoding failures after resolver admission produce
  `status = failed` receipts without escaping exceptions to the caller.
- Successful calls include workspace resolver receipt fields and operation
  metrics.
- Focused tests, changed-line coverage, full pre-commit, CI, and remote
  performance report pass without regressions.
