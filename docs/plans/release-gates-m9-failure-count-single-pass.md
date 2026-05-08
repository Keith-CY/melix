# Release Gates M9 Failure Count Single Pass

## Goal

Reduce redundant work in `evaluate_m9_release_evidence(...)` by classifying M9 release-gate failures in a single pass instead of scanning each section's failure list twice.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/release_gates.py`
- `services/mlx-worker-python/tests/test_release_gates.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/release_gates_m9_failure_count_probe.py`
- `infra/perf/pr_scoped_probes.json`
- this plan file

## Implementation

- Replace the suffix-based post-processing loop over `section_failures` with a counted section evaluator that returns missing and threshold-failure counts alongside the ordered failure strings.
- Preserve failure ordering, metric names, and summary values exactly while avoiding failure-string suffix scans in `evaluate_m9_release_evidence(...)`.

## Probe definition

Register `release-gates-m9-failure-count-single-pass` in the PR-scoped performance registry. The probe builds a synthetic M9 report/policy workload with many missing and below-threshold failures, calls `evaluate_m9_release_evidence(...)`, and reports:

- `elapsed_ms_mean` (lower is better)
- `endswith_checks_mean` (lower is better; structural signal, expected zero checks on head because the counted evaluator avoids post-processing failure strings)
- `failure_count_mean` (informational correctness guard)

## Verification commands

- Focused pytest for release gate and probe registry tests.
- Changed-scope coverage using `scripts/changed_scope_coverage.py` over the touched Python/test/script files.
- Local `scripts/pr_scoped_performance_run.py --probe-id release-gates-m9-failure-count-single-pass` base-vs-head probe against `origin/main`.
- `git diff --check`.
