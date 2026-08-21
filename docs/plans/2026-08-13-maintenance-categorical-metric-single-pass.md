# Maintenance categorical metric single-pass optimization

## Goal

Reduce allocation and unnecessary field reads in `MaintenanceCore._categorical_metric_code_for_samples` when maintenance benchmark metrics encode categorical sample fields.

The previous helper materialized every category value into a list and then built a `set` before deciding whether all samples had the same category or should report `mixed`. This slice keeps the same metric codes but scans once, returns `mixed` immediately on the first mismatch, and avoids list/set allocation.

## Linux-only constraint

This is a Python worker slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe. No Swift runtime validation is required.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_categorical_metric_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

`maintenance-categorical-metric-single-pass` covers the changed maintenance path.

The probe compares the previous list-plus-set helper against the current single-pass helper for two workloads:

1. Uniform categorical samples, where all samples must be scanned to prove the single category.
2. Mixed categorical samples, where the current helper can stop after the first mismatch.

Because this PR adds the probe script, the registered probe command resolves the script from the head worktree when the base worktree does not contain it yet. This keeps base/head metric comparison available for a newly registered command-json probe.

Reported metrics include current/legacy elapsed means, delta means, speedup ratios, sample counts, and peak bytes. The direct gate is the current mixed-category helper latency (`mixed_current_ms_mean`), which measures the optimized hot path directly. Legacy-derived delta and speedup ratios remain reported as informational context because CI variance in the legacy baseline can otherwise flag unrelated maintenance slices even when current-helper latency is stable or faster.

## Success criteria

- Existing categorical metric outputs are unchanged.
- The mixed-category workload keeps current-helper latency within the registered threshold.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe runs locally and in PR-scoped CI.
