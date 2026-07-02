# Runtime Export Smoke Waiver Direct Membership

## Status

Accepted slice for 2026-07-01 performance iteration.

## Scope

This slice keeps the runtime export smoke policy behavior unchanged while
removing one small allocation in the waiver path. `_waiver_for_load_failure()` no
longer materializes `allowed_waiver_reasons` into a temporary `set` before
checking for `EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED`.

## Probe Coverage

The affected code path is already covered by the registered PR-scoped probe
`runtime-export-smoke-policy` in `infra/perf/pr_scoped_probes.json` with focused
`test_command`, `coverage_command`, and `probe_command` entries. The probe emits
`elapsed_ms_mean`, `peak_bytes_mean`, target count, latency buckets, and waiver
counters.

## Validation Plan

- Add a regression test proving the waiver membership check does not materialize
  a temporary set.
- Run the focused runtime export smoke policy tests.
- Run the registered changed-scope coverage command.
- Run the registered runtime export smoke policy probe locally on Linux before
  pushing.
- Use the PR-scoped performance workflow as the merge gate.
