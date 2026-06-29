# Changed-scope diff parser splitlines slice

## Scope

This Python-only performance slice is limited to
`scripts/changed_scope_coverage.py::_parse_changed_lines()`. It keeps the
byte-oriented parser and changed-line semantics unchanged while using
`bytes.splitlines()` for the encoded diff line iteration instead of splitting on
an explicit newline byte separator.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Implementation plan

1. Start from a clean worktree synced to `origin/main`.
2. Confirm the registered probe covers the changed parser path.
3. Replace the parser's encoded diff iteration with `splitlines()` while
   preserving the existing empty-line handling branch for blank context lines.
4. Run focused tests and changed-scope coverage locally on Linux.
5. Run the registered probe locally against an `origin/main` baseline worktree
   and this branch.
6. Use GitHub Actions PR-scoped performance as the merge gate before squash
   merging.

## Verification boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
behavior is changed.
