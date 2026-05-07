# Changed-scope coverage diff parser first-character indexing

## Goal

Reduce per-line overhead in the hot changed-scope diff parser by avoiding a one-character string slice for every parsed diff line.

## Scope

This slice is limited to the Python changed-scope coverage parser and its registered PR-scoped diff-parser probe:

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-diff-parser`, which has focused `test_command`, `coverage_command`, and `probe_command` entries in `infra/perf/pr_scoped_probes.json`. The probe records:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `line_count`
- `file_count`
- `changed_line_count`

## Implementation plan

1. Preserve the existing literal dispatch semantics for diff headers, hunk headers, additions, deletions, and blank context lines.
2. Replace the hot `line[:1]` slice with direct first-character indexing guarded for empty lines.
3. Reuse the existing parser regression tests for behavior parity, including blank-line handling.
4. Compare the registered diff-parser probe against an `origin/main` baseline worktree before accepting the slice.

## Verification

- Focused changed-scope parser tests pass.
- Changed-scope coverage for the touched parser/probe/test scope remains at least 95%.
- The registered local probe reports lower `elapsed_ms_mean` versus the `origin/main` baseline.
- `git diff --check` passes.
