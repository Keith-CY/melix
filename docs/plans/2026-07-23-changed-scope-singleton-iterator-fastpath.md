# Changed-scope singleton iterator fast path

## Scope

This Python performance slice is limited to the singleton changed-line branch in `scripts/changed_scope_coverage.py`.

## Motivation

The registered `changed-scope-coverage-singleton-range-fastpath` probe models many files whose only changed line is outside the measured coverage ranges. That path intentionally returns before reading source text, but it still extracts the single changed line and checks measured range bounds for every file. This slice replaces `next(iter(changed))` with a direct one-item loop and collapses sorted executed/missing coverage lists into one combined bounds check before falling back to the existing unsorted-list behavior.

## Probe coverage

The affected path is covered by `changed-scope-coverage-singleton-range-fastpath` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches `scripts/changed_scope_coverage.py`, `scripts/changed_scope_coverage_singleton_probe.py`, the changed-scope tests, and PR-scoped performance registry tests.

## Plan

1. Keep the existing singleton no-source-read regression coverage in `tests/test_changed_scope_coverage.py`.
2. Change only the singleton changed-line extraction and sorted bounds check inside `_measurable_changed_lines(...)`.
3. Run the registered focused test, changed-scope coverage command, and probe locally on Linux.
4. Require the registered PR-scoped performance CI probe to complete successfully before merge.

## Success criteria

- Focused changed-scope coverage and PR-scoped registry tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered `changed-scope-coverage-singleton-range-fastpath` probe reports neutral-to-lower `elapsed_ms_mean` with `source_read_calls_mean=0`.
- PR-scoped performance CI completes successfully before merge.
