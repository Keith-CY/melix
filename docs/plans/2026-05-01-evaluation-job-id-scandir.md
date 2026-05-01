# Evaluation Job ID Scandir Optimization Plan

## Goal

Reduce evaluation job-id allocation overhead when an evaluation jobs directory already contains many persisted runs.

## Linux Verification Scope

This slice is limited to Python worker code and the registered PR-scoped performance probe, so it is fully verifiable on Linux.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `docs/plans/2026-05-01-evaluation-job-id-scandir.md`

## Registered Probe

The affected path is already covered by the `evaluation-job-id-high-water-mark` entry in `infra/perf/pr_scoped_probes.json`:

- `watch_globs` includes `services/mlx-worker-python/worker/engine/evaluation_core.py` and the focused tests.
- `test_command` runs the evaluation job-id regression tests and PR-scoped performance probe dispatch checks.
- `coverage_command` measures changed-scope coverage for `evaluation_core.py` and `pr_scoped_performance.py`.
- `probe_command` runs `_probe_evaluation_job_id(...)`, which seeds 2,000 existing `eval-NNNN` run directories and allocates 200 new job IDs.

## Optimization Slice

Replace the `_prime_next_job_index(...)` `Path.iterdir()` loop with an `os.scandir()` loop that reads `DirEntry.name` and checks directories with `follow_symlinks=False`. This avoids allocating `Path` objects for every existing run directory while preserving the same high-water-mark semantics.

## Success Metrics

- Functional behavior remains unchanged for existing and conflicting `eval-NNNN` run directories.
- Changed-scope coverage remains at least 95%.
- The registered `evaluation-job-id-high-water-mark` probe should show lower `elapsed_ms_mean` and `per_call_ms_mean` versus the `origin/main` baseline.

## Verification Commands

- Registered focused `test_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `coverage_command` from `infra/perf/pr_scoped_probes.json`.
- Registered `probe_command` from `infra/perf/pr_scoped_probes.json`, run locally before and after the implementation.
- `git diff --check`.
