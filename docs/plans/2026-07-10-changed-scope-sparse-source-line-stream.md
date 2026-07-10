# Changed-Scope Sparse Source-Line Streaming

## Scope

This performance slice narrows the source-line filtering step in
`scripts/changed_scope_coverage.py` when only a small number of changed lines are
measurable for a file.

## Motivation

Changed-scope coverage currently avoids most work before reading source files,
but once a sparse changed set overlaps measured coverage it reads and splits the
entire source file just to filter blank/comment-only changed lines. Small PRs
commonly touch only a few measured lines, so this can add unnecessary file
materialization on large files.

## Plan

- Preserve existing range-overlap and dense measured-set logic.
- For sparse measurable changed-line sets, stream the source file only until all
  target lines are seen, then classify blank/comment lines from those stripped
  lines.
- Keep the full-file read path for dense measured sets where materializing all
  lines remains simpler and predictable.
- Extend the registered changed-scope coverage measured-set probe with a sparse
  changed-line scenario.

## Probe

Registered PR-scoped probe: `changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`.

Relevant metrics:

- `sparse_elapsed_ms_mean`: lower is better for sparse changed-line filtering.
- `sparse_source_read_calls_mean`: lower is better and should remain zero for
  full-file `Path.read_text` calls in the sparse branch.
- Existing dense and allowlist metrics continue to guard unchanged hot paths.

## Verification

Run the registered test command, coverage command, and probe command locally on
Linux before opening the PR. CI remains the canonical PR-scoped performance
comparison against `origin/main`.
