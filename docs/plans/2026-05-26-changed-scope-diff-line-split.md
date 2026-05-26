# Changed-Scope Coverage Diff Line Split Fast Path

## Scope

This Python-only performance slice is limited to the changed-scope coverage unified-diff parser in `scripts/changed_scope_coverage.py`.

The parser already dispatches hot-loop work from the first character. This slice keeps that behavior and changes line iteration from `str.splitlines()` to `str.split("\n")` for the Git unified diff payload returned by `git diff --unified=0`. Git diff output is line-feed delimited in this workflow, so the change avoids the broader universal-newline handling that is not needed on the registered probe path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.

The registry entry already provides:

- focused `test_command` coverage for parser behavior and probe registry selection;
- focused `coverage_command` for changed-scope coverage on the touched parser/probe/test files;
- `probe_command` using `scripts/changed_scope_coverage_parse_probe.py`, which builds a deterministic synthetic multi-file unified diff and reports `elapsed_ms_mean`, `elapsed_ms_min`, `line_count`, `file_count`, and `changed_line_count`.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. The GitHub PR-scoped performance workflow remains the merge gate for registered base-vs-head validation before merge.
