# Changed Scope Coverage Diff Header Inline Parse

## Goal

Reduce per-line overhead in `scripts/changed_scope_coverage.py` while parsing large zero-context git diffs for changed-scope coverage checks.

## Scope

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py` (existing parser behavior coverage)
- `scripts/changed_scope_coverage_parse_probe.py`
- `infra/perf/pr_scoped_probes.json` registered probe: `changed-scope-coverage-diff-parser`

## Registered probe

The affected path is already covered by the PR-scoped performance probe `changed-scope-coverage-diff-parser`, which provides focused `test_command`, `coverage_command`, and `probe_command` entries. The probe parses a synthetic multi-file diff and reports:

- `elapsed_ms_mean` (lower is better)
- `elapsed_ms_min` (informational)
- `line_count`, `file_count`, and `changed_line_count` (correctness/informational)

## Slice

Inline the diff-header new-path extraction inside `_parse_changed_lines` after the hot-loop prefix dispatch has already proven that the line starts with `diff --git a/`. This avoids a second helper call and a duplicate `startswith` check for every diff header while preserving the standalone helper for direct tests and external call sites.

## Linux verification

This is a Python helper slice and is locally verifiable on Linux with the registered focused tests, changed-scope coverage command, and `scripts/changed_scope_coverage_parse_probe.py`.

## Success metrics

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local registered probe shows lower `elapsed_ms_mean` than the same worktree baseline.
- Git diff check passes.
