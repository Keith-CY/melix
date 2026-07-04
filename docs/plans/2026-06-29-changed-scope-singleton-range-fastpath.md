# Changed-scope singleton range fast path

## Context

`scripts/changed_scope_coverage.py` compares the changed-line set for a file
against executed and missing line ranges from `coverage json`. Most focused
slice diffs change only one executable line in a file. In that singleton case,
`_line_ranges_may_overlap` can compare the one changed line directly against the
coverage ranges instead of scanning the changed set twice with `min(changed)` and
`max(changed)`.

## Slice

This Python-only slice is limited to changed-scope coverage tooling:

- add a singleton changed-line fast path in `_line_ranges_may_overlap`;
- preserve the existing empty, singleton measured-entry, sorted-list, and
  reversed-list fallbacks;
- register a PR-scoped performance probe for the singleton changed-line shape.

## Registered probe

The affected path is covered by the new registered PR-scoped probe
`changed-scope-coverage-singleton-range-fastpath` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries. It measures many
files with one changed line just outside large measured coverage ranges and
reports:

- `elapsed_ms_mean` (lower is better);
- `source_read_calls_mean` (must remain `0.0`);
- `path_count` and `measured_lines_per_path` as informational context.

## Verification

Run the registered focused tests, changed-scope coverage command, and the local
registered probe on Linux before opening the PR. The PR-scoped performance
workflow remains the merge gate for the registered probe result in CI.
