# Changed-scope diff parser splitlines

## Scope

This performance slice targets `scripts/changed_scope_coverage.py` and the registered PR-scoped probe `changed-scope-coverage-diff-parser`.

## Plan

- Keep the existing prefix-dispatch parser semantics for git diff output.
- Replace the explicit `split("\n")` line materialization with `splitlines()` in `_parse_changed_lines` so the hot parser loop avoids producing a synthetic trailing empty record for normal newline-terminated diff output.
- Preserve line-number accounting for blank context lines, additions, deletions, malformed hunks, and no-newline markers.

## Validation

- Focused parser regression coverage keeps multiple-file/multiple-hunk parsing stable and now asserts equivalent output for newline-terminated diff text.
- Registered probe: `scripts/changed_scope_coverage_parse_probe.py` reports parser elapsed time for a synthetic multi-file diff under the `changed-scope-coverage-diff-parser` PR-scoped probe.
