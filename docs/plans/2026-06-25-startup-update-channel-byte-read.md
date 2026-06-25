# Startup Update Channel Byte Read Performance Slice

## Scope

This Python-only performance slice is limited to
`worker.productization.startup_signals.check_for_updates()`. It preserves update
channel behavior while parsing the channel JSON from bytes and reusing the
resolved channel path for the missing-version diagnostic.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for startup
signals. This slice extends the existing probe script and registry metrics with
update-channel read metrics:

- `update_channel_elapsed_ms_mean`
- `update_channel_peak_bytes_mean`
- `update_channel_result_available`

## Expected Behavior

- Valid update channel JSON still reports newer and up-to-date versions with the
  same payload fields.
- Missing `latest_version` diagnostics still include the resolved channel path.
- `check_for_updates()` avoids `Path.read_text()` and parses `Path.read_bytes()`
  payloads directly.

## Verification Plan

Run the registered focused startup-signals tests, changed-scope coverage, and
the registered `startup-signals-version-compare-single-pass` probe locally on
Linux before pushing. GitHub Actions PR-scoped performance remains the final
merge gate.
