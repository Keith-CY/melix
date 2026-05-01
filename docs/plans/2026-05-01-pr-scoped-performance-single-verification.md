# PR-Scoped Performance Single-Verification Optimization Plan

## Goal

Reduce redundant head-side verification work in the PR-scoped performance harness by avoiding a standalone focused `pytest` run when the selected probe's `coverage_command` already reruns the same focused tests under coverage.

## Linux-Only Constraint

This change is limited to the Python PR-scoped performance harness and its tests so it can be fully verified on Linux without relying on macOS or Swift-only execution paths.

## Touched Files

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

- Extend `ProbeDefinition` with an explicit flag that tells the harness the probe's `coverage_command` already replays the focused tests.
- Make `_run_head_verification(...)` skip the standalone `test_command` for those probes and treat the coverage run as the gating verification step.
- Keep backward compatibility for probes that still need separate `test_command` and `coverage_command` execution.
- Add focused regression tests for the new verification flow and registry behavior.

## Performance Probe

Measure head-side verification wall time for a representative Python probe (`benchmark-evaluation-report-running-aggregates`) by timing `_run_head_verification(...)` against:

- `origin/main` worktree baseline
- current branch implementation

The probe is a local Python timing script that runs the same registry-selected verification path and reports mean elapsed milliseconds.

## Success Metrics

- Functional behavior remains unchanged for current probe registry entries.
- Changed executable scope coverage is at least 95%.
- Representative head verification wall time is measurably lower than `origin/main` because the duplicated standalone `pytest` invocation is removed.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `git diff --check`
- Local timing probe comparing `origin/main` against the branch implementation for `_run_head_verification(...)`
