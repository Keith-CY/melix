# Changed-Scope Coverage Hunk Parser Micro-Optimization

## Linux-only constraint

This slice is Python tooling only. It can be verified locally on Linux with the focused changed-scope coverage tests, changed-scope coverage reporting, and the registered PR-scoped performance probe.

## Optimization

`changed_scope_coverage._parse_hunk_new_start()` runs once for every hunk in the changed-scope coverage diff parser. The previous implementation scanned the new-range digits, sliced the digit substring, and then called `int()` on that substring.

This slice keeps the parser behavior unchanged while accumulating the integer value during the digit scan. That removes one short-lived string allocation per parsed hunk and keeps the hot path single-pass.

## Registered probe

Existing registered probe: `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.

The probe covers:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The registry already defines focused `test_command`, `coverage_command`, and `probe_command` entries, so no probe registry change is needed for this narrow parser optimization.

## 2026-07 byte-method binding slice

This follow-up slice stays within `_parse_changed_lines(...)` and only binds
`bytes.find` / `bytes.startswith` once before the diff-line loop. The parser
still dispatches by first byte and preserves ordinary context lines that happen
to start with `d`; the change removes repeated bound-method lookup overhead for
diff headers and hunk headers in the registered synthetic parser workload.

## 2026-07-31 addition-line dispatch slice

This follow-up slice stays within `_parse_changed_lines(...)` and only reorders
post-hunk line dispatch after the parser has an active file and hunk. The
registered synthetic diff workload contains more added lines than minus or
`\\ No newline` marker lines, so the parser now handles `+` additions before the
less-common minus and backslash-marker branches. Behavior is unchanged: additions
are still recorded at the current new-file line, removals and no-newline markers
still do not advance `new_line`, and ordinary context lines still advance it.

## Verification plan

Run the registered focused tests, changed-scope coverage, and local registered probe before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.
