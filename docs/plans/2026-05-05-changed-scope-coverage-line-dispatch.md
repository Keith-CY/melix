# Changed-scope coverage parser line dispatch

## Goal

Reduce hot-loop prefix checks in `scripts/changed_scope_coverage.py` by dispatching unified diff parser branches from the first character before falling back to full prefix matching.

## Scope

This slice is Python-only and limited to the changed-scope coverage diff parser path. It keeps parser output identical while reducing repeated `str.startswith(...)` work for ordinary context, deletion, addition, hunk, and file-marker lines.

## 2026-07 dense measured-line intersection slice

This follow-up slice is limited to the dense changed-line filter in
`scripts/changed_scope_coverage.py`. When the changed line set is large enough
to scan measured coverage lines instead of bisecting every changed line, the
implementation can use C-level `set.intersection(...)` against the executed and
missing line lists. The fallback path still supports generic `Set[int]`
implementations, and coverage classification remains identical.

## 2026-07 sparse measured-line membership binding slice

This follow-up slice is limited to the sparse measured-line fallback in
`_measurable_changed_lines(...)`. It keeps the bisect-based membership helper but
binds it once per measured-file path before the changed-line list comprehension,
reducing repeated global lookups while preserving the dense `set.intersection`
path and all coverage classification semantics.

## Registered performance probe

The affected path is already covered by the registered PR-scoped probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries. The probe builds a deterministic synthetic multi-file diff and reports:

- `elapsed_ms_mean` (lower is better)
- `line_count` and `changed_line_count` guard-rail metrics

The dense measured-line filter slice is covered by the registered PR-scoped
probe `changed-scope-coverage-measured-set-filter`, including focused
`test_command`, `coverage_command`, and `probe_command` entries. Its metrics
include `dense_elapsed_ms_mean` for the changed-path measured-line scan,
`source_read_calls_mean`, and `dense_source_read_calls_mean` guard rails.

## Verification plan

- Run the focused parser and PR-scoped registry tests.
- Run changed-scope coverage for the touched files and require at least 95% changed-line coverage.
- Run the registered parser probe locally on Linux against both `origin/main` and this branch via `scripts/pr_scoped_performance_run.py`.
- For the dense measured-line slice, run the registered
  `changed-scope-coverage-measured-set-filter` probe locally on Linux against
  both `origin/main` and this branch via `scripts/pr_scoped_performance_run.py`.
- Use the GitHub PR-scoped performance workflow as the merge gate after opening the PR.

## Success criteria

- Parser tests preserve multi-file, hunk, marker, blank-context, and added-content semantics.
- Changed-scope coverage is at least 95% for the touched executable lines.
- Local and CI probe metrics show a clear non-regression or improvement for `elapsed_ms_mean` with unchanged guard-rail counts.

## 2026-08-10 non-addition branch collapse slice

This slice is limited to the `_parse_changed_lines(...)` hot loop after a hunk
has established the active new-line counter. It preserves the existing first-byte
dispatch and addition handling, while collapsing the deletion and backslash
skip branches into one negative check before ordinary context line accounting.
Parser semantics remain unchanged for additions, deletions, `\\ No newline...`
markers, blank context lines, and ordinary context lines.

Registered probe: `changed-scope-coverage-diff-parser` in
`infra/perf/pr_scoped_probes.json`. The probe already covers
`scripts/changed_scope_coverage.py`, the parser probe script, focused parser
unit tests, changed-scope coverage, and PR-scoped probe registry validation.

## 2026-08-14 sorted measured-line target reuse slice

This follow-up slice is limited to `_measurable_non_comment_lines(...)` in the
changed-scope coverage measured-line path. The upstream caller already sorts the
measured changed-line list before reading source text, so the common path can
reuse that sorted list instead of always allocating a `sorted(...)` copy. Direct
callers that provide unsorted line numbers still receive ascending output through
the fallback copy/sort path.

Registered probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused tests, changed
scope coverage, and the local/CI command-json probe for sparse and dense
measured-line scans.

## 2026-08-14 dense ASCII comment-prefix fast path slice

This follow-up slice is limited to the dense-source blank/comment filter in
`_measurable_non_comment_lines(...)`. After the existing `strip()` call has
preserved whitespace and Unicode line-numbering semantics, the dense branch's
comment test uses a direct first-character comparison instead of a
`str.startswith("#")` method call. Blank lines remain guarded before indexing,
indented comments still strip to `#`, and sparse measured-line filtering remains
unchanged.

Registered probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe covers the same focused tests,
changed-scope coverage command, and local/CI command-json metrics for sparse and
dense measured-line scans.

## 2026-08-16 sparse ASCII comment-prefix fast path slice

This follow-up slice is limited to the sparse-source blank/comment filter in
`_measurable_non_comment_lines(...)`. It mirrors the dense branch's direct
first-character comment test after the existing `strip()` call and keeps the
same blank-line guard before indexing. Duplicate target-line handling,
out-of-range skipping, sorted-input behavior, and Unicode newline semantics stay
unchanged.

Registered probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe includes the sparse scan metric
`sparse_elapsed_ms_mean`, focused tests, changed-scope coverage, and local/CI
command-json metrics for the changed-scope measured-line path.

## 2026-08-18 measurable append binding slice

This follow-up slice is limited to `_measurable_non_comment_lines(...)` in the
changed-scope coverage measured-line path. The dense and sparse source filters
now bind `measurable.append` once before their hot loops, preserving the same
blank/comment filtering, duplicate target-line behavior, out-of-range skipping,
and sorted-output contract while avoiding repeated list attribute lookups.

Registered probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused parser and
measured-line tests, changed-scope coverage, and local/CI command-json metrics
for `elapsed_ms_mean`, `sparse_elapsed_ms_mean`, and `dense_elapsed_ms_mean`.

## 2026-08-20 dense source split fast path slice

This follow-up slice is limited to the dense-source branch in
`_measurable_non_comment_lines(...)`. Instead of building the same full line list
through the file object's Python-level `readlines()` loop, the branch reads the
source text once, normalizes universal newline delimiters explicitly, and splits
on literal `\n`. This preserves the existing line-numbering contract (including
`\r` and `\r\n` handling without treating vertical-tab/form-feed/Unicode
separators as new source lines) while moving dense fixture splitting into faster
C-level string operations. Sparse source filtering and changed-line partitioning
remain unchanged.

Registered probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe reports `dense_elapsed_ms_mean`,
`sparse_elapsed_ms_mean`, and `elapsed_ms_mean`; CI remains the merge gate for
the registered PR-scoped performance report.
