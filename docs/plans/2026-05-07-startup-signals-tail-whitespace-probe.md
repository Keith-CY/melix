# Startup Signals Tail Whitespace Probe Optimization

## Goal

Reduce Python-level work in startup log excerpt parsing when logs contain large trailing whitespace blocks, while preserving startup failure classification behavior.

## Linux-only constraint

This slice touches Python-only startup diagnostics and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Use the existing registered probe ID `startup-signals-lazy-worker-log-excerpts`, extended with tail-scan metrics:

- `tail_scan_elapsed_ms_mean`
- `tail_scan_peak_bytes_mean`
- `trailing_whitespace_bytes`

The probe writes a synthetic log ending in `80,000` whitespace bytes, repeatedly calls `_read_last_nonempty_line(...)`, and verifies that the final non-empty line remains unchanged.

## Implementation note

This slice keeps the reverse chunk scan semantics but combines trailing-whitespace
skipping and last-line-bound discovery into a single helper. `_read_last_nonempty_line(...)`
now avoids a second reverse scan after finding the last non-whitespace byte and
returns the already-trimmed payload without a second decoded-string `rstrip()`.

## Success metrics

- Focused startup signal tests pass.
- Changed-scope coverage is at least 95%.
- `git diff --check` is clean.
- Local probe reports concrete tail-scan timing and allocation numbers.
- PR-scoped performance CI selects and runs `startup-signals-lazy-worker-log-excerpts`.
