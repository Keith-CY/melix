# Startup update result cache slice

This Python performance slice is limited to `worker.productization.startup_signals.check_for_updates(...)`.

## Goal

Keep update-check behavior unchanged while avoiding repeated channel JSON decode,
`UpdateCheckResult` allocation, and version comparison work for repeated checks
against the same stat-valid channel file and installed version. The channel file
stat/cache path remains the source of freshness for `latest_version` and
`channel`; this slice memoizes the immutable final result tuple only while the
channel file `mtime_ns` and size are unchanged.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The registered entry already includes focused `test_command`, `coverage_command`, and `probe_command` commands, and the `update_channel_*` / `update_result_*` metrics cover repeated update-check result construction.

## Verification plan

1. Add regression tests proving repeated checks reuse the stat-valid cached
   result before re-decoding channel JSON, and that a changed channel file
   refreshes the cached result.
2. Run the registered focused test command for `startup-signals-version-compare-single-pass`.
3. Run the registered changed-scope coverage command.
4. Run the registered probe locally on Linux and use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior changes are included.
