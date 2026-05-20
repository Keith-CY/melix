# PR-Scoped Performance Report Result Path List Slice

## Scope

This Python tooling performance slice is limited to result-file discovery in
`scripts/pr_scoped_performance_report.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`pr-scoped-performance-report-results-scandir` in
`infra/perf/pr_scoped_probes.json`. The registry entry already defines focused
`test_command`, `coverage_command`, and `probe_command` entries for the report
loader, probe script, and PR-scoped performance tests.

## Optimization

`_load_results()` now materializes matching `os.scandir()` paths into a list,
sorts the list in place, and binds the hot `results.append` and `json.loads`
lookups once before the per-file loop. This keeps the existing `os.scandir()` and
binary JSON read behavior while avoiding the `sorted(generator)` path and repeated
attribute lookups for the hot result-file loader used by PR-scoped performance
reporting.

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally and require the
   repository's 95 percent changed-scope threshold.
3. Run the registered probe locally on Linux with repeated baseline and head
   samples, comparing `elapsed_ms_mean` and `elapsed_ms_min` for 2,000 synthetic
   result JSON files.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Acceptance

- Focused tests and changed-scope coverage pass.
- The local registered probe is neutral-to-improved for `elapsed_ms_mean` while
  preserving `result_count=2000.0`.
- PR-scoped performance CI selects and runs
  `pr-scoped-performance-report-results-scandir` before merge.
