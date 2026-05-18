# Integration remove-tree local bindings performance slice

## Scope

This Python-only slice is limited to `tests/integration/helpers.py` and the
registered integration cleanup probe path. It keeps `LiveMelixStack._remove_tree`
semantics unchanged while reducing per-directory stack tuple allocation inside the
`os.scandir()` cleanup loop.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`integration-swift-binary-resolution-scandir` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports the
remove-tree timing/peak-memory metrics emitted by
`scripts/integration_remove_tree_probe.py`.

## Implementation plan

1. Reuse the existing focused remove-tree behavior tests to preserve cleanup
   parity for nested files, symlinks, missing roots, and disappearing entries.
2. Keep the non-recursive post-order traversal but replace `(path, visited)`
   stack tuples with a single sentinel marker plus path entries. This removes one
   tuple allocation per stack push while preserving bounded stack behavior.
3. Run the registered focused tests, changed-scope coverage, and PR-scoped probe
   locally on Linux against an `origin/main` baseline worktree and this branch.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Verification notes

Local Linux verification can validate Python behavior and probe direction. This
slice does not change Swift runtime behavior; Swift binary-resolution metrics in
the shared registered probe remain CI-reported context, while the remove-tree
metrics are directly affected by this Python helper change.
