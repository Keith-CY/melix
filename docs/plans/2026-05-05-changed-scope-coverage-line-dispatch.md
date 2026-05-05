# Changed-scope coverage parser line dispatch

## Goal

Reduce hot-loop prefix checks in `scripts/changed_scope_coverage.py` by dispatching unified diff parser branches from the first character before falling back to full prefix matching.

## Scope

This slice is Python-only and limited to the changed-scope coverage diff parser path. It keeps parser output identical while reducing repeated `str.startswith(...)` work for ordinary context, deletion, addition, hunk, and file-marker lines.

## Registered performance probe

The affected path is already covered by the registered PR-scoped probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries. The probe builds a deterministic synthetic multi-file diff and reports:

- `elapsed_ms_mean` (lower is better)
- `line_count` and `changed_line_count` guard-rail metrics

## Verification plan

- Run the focused parser and PR-scoped registry tests.
- Run changed-scope coverage for the touched files and require at least 95% changed-line coverage.
- Run the registered parser probe locally on Linux against both `origin/main` and this branch via `scripts/pr_scoped_performance_run.py`.
- Use the GitHub PR-scoped performance workflow as the merge gate after opening the PR.

## Success criteria

- Parser tests preserve multi-file, hunk, marker, blank-context, and added-content semantics.
- Changed-scope coverage is at least 95% for the touched executable lines.
- Local and CI probe metrics show a clear non-regression or improvement for `elapsed_ms_mean` with unchanged guard-rail counts.
