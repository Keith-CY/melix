# Startup Failure Report Slots Slice

## Scope

This Python-only performance slice is limited to the startup failure classification result object in `services/mlx-worker-python/worker/productization/startup_signals.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `startup-signals-lazy-worker-log-excerpts` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/startup_signals_log_probe.py`

This slice extends the existing probe metrics with `report_alloc_elapsed_ms_mean`, `report_alloc_peak_bytes_mean`, and `report_has_dict_mean` so the allocation impact of slots is measured directly alongside the existing startup failure classification timings.

## Optimization Slice

`StartupFailureReport` is allocated on every startup failure classification path. This slice adds dataclass slots to remove the per-instance `__dict__` while preserving the frozen dataclass API and `to_dict()` payload.

The change intentionally does not modify log-reading decisions, classification labels, summaries, or manifest fields.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before pushing. Compare the registered probe output against a pre-change baseline captured from `origin/main` in the same worktree.

CI remains the merge gate for the registered PR-scoped performance report.

## Follow-up Slice: Manual `to_dict()` Snapshot

The next startup-report micro-slice keeps the same registered probe and narrows
scope to `StartupFailureReport.to_dict()`. The previous implementation used
`dataclasses.asdict()`, which recursively walks dataclass fields even though the
report payload contains only scalar values. This slice replaces that generic
walk with an explicit field dictionary while preserving the public keys and
values.

The registered probe now also reports `report_to_dict_elapsed_ms_mean`,
`report_to_dict_peak_bytes_mean`, and an informational
`report_to_dict_checksum` so the PR-scoped performance workflow measures the
serialization hot path directly.
