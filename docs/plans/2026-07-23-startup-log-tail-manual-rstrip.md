# Startup log tail whitespace chunk fast path

This Python-only performance slice is limited to startup failure log excerpt handling in `worker.productization.startup_signals._read_last_nonempty_line()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.

The probe watches:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`
- `infra/perf/pr_scoped_probes.json`

The registered probe reports classification costs plus the direct tail-scan metrics `tail_scan_elapsed_ms_mean`, `tail_scan_peak_bytes_mean`, and `trailing_whitespace_bytes`.

## Optimization

Startup logs can end with large trailing whitespace runs after the last useful line. `_seek_last_nonempty_line_bounds()` previously called `bytes.rstrip(_BYTE_WHITESPACE)` for each backward chunk while finding the last non-empty byte. For chunks that are entirely whitespace, `rstrip()` still constructs a stripped bytes object before the scan can continue.

This slice adds a small `_right_stripped_chunk_length()` helper that uses the C-level `bytes.isspace()` predicate to short-circuit all-whitespace chunks to length `0`, preserving the existing `rstrip()` behavior for mixed chunks. This keeps behavior unchanged while reducing allocation and elapsed time for logs with large whitespace tails.

## Verification plan

1. Run the new focused regression test and the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered local probe before and after the implementation and compare `tail_scan_elapsed_ms_mean` and related startup classification metrics.
4. Use the PR-scoped performance GitHub Actions report as the merge gate.
