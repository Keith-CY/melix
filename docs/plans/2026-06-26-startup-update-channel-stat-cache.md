# Startup update channel stat-valid cache

## Scope

This Python performance slice is limited to `check_for_updates(...)` in
`services/mlx-worker-python/worker/productization/startup_signals.py`.
The hot path repeatedly checks the same update-channel JSON file while building
startup signals. The previous implementation reparsed the channel JSON on every
call, even when the channel file had not changed.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports
`update_channel_elapsed_ms_mean` plus `update_channel_peak_bytes_mean` for the
channel-read path.

This slice extends the focused command lists with the new regression test
`test_check_for_updates_reuses_stat_valid_channel_cache` so local and CI probe
validation execute the cache behavior guard.

## Plan

1. Add a regression test proving repeated checks of an unchanged channel file
   avoid a second `Path.read_bytes()` call.
2. Add a small stat-valid cache keyed by the resolved update-channel path and
   invalidated by `st_mtime_ns` and `st_size`.
3. Keep `check_for_updates(...)` behavior equivalent for available, up-to-date,
   and missing-version channel payloads.
4. Run focused tests, changed-scope coverage, and the registered probe locally
   on Linux before pushing. GitHub Actions PR-scoped performance remains the
   merge gate.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
performance claims are made by this change.
