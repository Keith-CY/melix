# Changed-scope diff current-set cache optimization

## Goal

Reduce per-addition overhead in `scripts/changed_scope_coverage.py` while parsing large unified diffs. The hot parser currently looks up `changed_by_path[current_path]` for every added line even though a hunk belongs to a single active file.

## Scope

- `scripts/changed_scope_coverage.py`
- Existing registered probe coverage in `infra/perf/pr_scoped_probes.json`
- Existing focused tests for `tests/test_changed_scope_coverage.py` and PR-scoped probe selection

## Registered probe

The affected path is covered by the registered `changed-scope-coverage-diff-parser` PR-scoped probe. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and measures:

- `elapsed_ms_mean` (lower is better)
- `changed_line_count` (informational)
- `line_count` (informational)

This slice also keeps the registered command compatible with the repository's `python3` invocation policy for the touched probe.

## Optimization hypothesis

Cache the active file's changed-line set when parsing a `diff --git` header, then append additions directly to that set inside the hunk loop. This should preserve behavior while avoiding repeated dictionary lookups in the parser's inner loop.

## Validation plan

1. Run the focused registered tests.
2. Run changed-scope coverage through the registered coverage command.
3. Run the registered probe locally on Linux before and after the change, with at least three samples each.
4. Require the local probe direction to improve before opening the PR.
5. Require PR-scoped performance CI to select and complete `changed-scope-coverage-diff-parser` before merge.
