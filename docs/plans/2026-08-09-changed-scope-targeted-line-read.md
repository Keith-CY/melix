# Changed-scope targeted line read slice

## Scope

This Python-only performance slice is limited to `_measurable_non_comment_lines()` in `scripts/changed_scope_coverage.py`.

The helper classifies changed source lines as measurable code, blank, or comment lines for the changed-scope coverage gate. Sparse changed-line sets currently only need a few source lines, but the helper reads the entire file before checking those target line numbers.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` commands and reports `elapsed_ms_mean`, `sparse_elapsed_ms_mean`, `dense_elapsed_ms_mean`, and `allowlist_parse_elapsed_ms_mean`.

## Plan

1. Preserve existing newline semantics by iterating the file object directly rather than using `str.splitlines()`.
2. Sort the requested line numbers once, use the existing dense `readlines()` path for broad changed sets, and stream sparse file reads only until the final target line has been classified.
3. Preserve duplicate target behavior for defensive compatibility with the existing helper contract.
4. Run focused tests, changed-scope coverage, and the registered measured probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.

## Success criteria

- Focused changed-scope coverage tests pass.
- Changed-scope coverage remains at least 95 percent for the touched scope.
- The local registered probe shows lower `sparse_elapsed_ms_mean` and non-regressing overall `elapsed_ms_mean` without materially regressing dense-path metrics.
