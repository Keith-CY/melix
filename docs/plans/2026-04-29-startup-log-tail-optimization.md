# Startup Log Tail Optimization For Linux-Verified Python Worker Slice

## Summary

Optimize Melix startup failure classification in `services/mlx-worker-python/worker/productization/startup_signals.py` so it extracts only the final log line needed for diagnostics instead of materializing entire log files in memory.

## Scope

- Touched code:
  - `services/mlx-worker-python/worker/productization/startup_signals.py`
- Touched tests:
  - `services/mlx-worker-python/tests/test_startup_signals.py`
- Linux-only verification path:
  - targeted `pytest`
  - changed-scope `coverage`
  - explicit synthetic performance probe against large log files

## Why This Slice

`classify_startup_failure()` only needs the most recent line from each configured log file. The current `_log_excerpt()` helper reads each whole file, strips it, then keeps only `splitlines()[-1]`. That creates avoidable I/O and memory pressure when startup logs are large.

## Implementation Plan

1. Add a focused failing test that proves `_log_excerpt()` / `classify_startup_failure()` still returns the last non-empty line from a log with trailing blank lines.
2. Replace full-file `read_text()` usage with a bounded tail reader that seeks from the end of the file and decodes only the bytes needed to recover the last line.
3. Keep missing-file and empty-file behavior unchanged.
4. Re-run the targeted startup-signals tests and measure changed-scope coverage.
5. Run a synthetic probe that compares current behavior metrics for startup failure classification on a large generated log file and record wall-clock plus peak-memory numbers.

## Success Metrics

- Functional output remains identical for the startup failure classification cases covered by tests.
- Changed executable file coverage is at least 95%.
- Synthetic probe shows materially lower peak memory for large-log classification.

## Verification Commands

- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py`
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py`
- `PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/startup_signals.py services/mlx-worker-python/tests/test_startup_signals.py`
- synthetic Python performance probe under `/tmp` for large log excerpts
- `git diff --check`
