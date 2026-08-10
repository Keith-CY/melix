# Changed-scope coverage inline hunk-start parser

## Scope

This Python-only performance slice is limited to the unified-diff parser inside
`scripts/changed_scope_coverage.py`, specifically the hot `@@ ... +<line>` hunk
header path used by `_parse_changed_lines(...)`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization hypothesis

The parser already works on bytes to avoid repeatedly allocating text lines.
Large PR diffs can still contain thousands of hunk headers, and each header
previously paid an extra Python helper-call dispatch to parse the new-file start
line number. Inlining the small byte-digit loop into `_parse_changed_lines(...)`
keeps the same accepted grammar while avoiding the helper dispatch on every hunk
header.

## Validation plan

1. Keep the change to one parser hot-path slice and preserve existing diff
   semantics.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux and require
   at least 95% for the touched scope.
4. Run the registered probe locally and compare against the pre-change baseline
   captured from the same worktree before editing.
5. Use PR-scoped performance CI as the final registered probe gate before merge.
