# Startup Signals Tail-Window Performance Slice

## Goal

Reduce avoidable small backward reads while classifying startup failures whose
log files end with long whitespace tails. Keep the existing diagnostic contract:
only the last non-empty line is decoded, missing logs are skipped by read
fallback, and direct error-text classifications avoid log reads entirely.

## Scope

This slice is Python-only and limited to `worker.productization.startup_signals`
and its focused tests. It does not change manifest fields, startup failure
classification names, or operator-facing messages.

## Registered Probe

The affected path is covered by the existing PR-scoped probe
`startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and reports:

- `tail_scan_elapsed_ms_mean` (lower is better)
- `tail_scan_peak_bytes_mean` (lower is better)
- direct classification read/exists counts (lower is better)

## Implementation Plan

1. Keep focused regression coverage around CR-only, LF, invalid UTF-8, and
   whitespace-only tail behavior.
2. Change only `_seek_last_nonempty_line_bounds` so the hot path first searches
   for the common LF delimiter and only falls back to CR when needed, avoiding a
   second full-chunk reverse scan for normal newline-terminated logs.
3. Preserve exact last-line bounds and UTF-8 replacement decoding behavior.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_startup_signals.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_startup_signals.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/startup_signals.py \
  services/mlx-worker-python/tests/test_startup_signals.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/startup_signals_log_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id startup-signals-lazy-worker-log-excerpts \
  --base-repo <baseline-worktree> \
  --head-repo "$PWD" \
  --output /tmp/startup-signals-tail-window-probe.json
```
