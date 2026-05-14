# Release gates metric value local binding optimization

This Python-only performance slice is limited to `services/mlx-worker-python/worker/productization/release_gates.py`.

## Scope

The M9 release-gate evaluator resolves many policy metric names inside `_evaluate_section_metrics_with_counts(...)`. This slice keeps the release-gate policy semantics unchanged and only binds `_metric_value` and the missing sentinel to local variables before the hot rules loop so each metric check avoids repeated global-name resolution.

## Registered probe

The affected path is covered by the registered PR-scoped probe `release-gates-m9-failure-count-single-pass` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the M9 release-gate evaluator and probe script.

## Verification plan

Run the registered focused tests, changed-scope coverage, and the registered local probe on Linux before pushing. Accept the slice only if behavior remains identical and the registered probe shows a stable elapsed-time improvement without changing `failure_count_mean` or `endswith_checks_mean`.

## Linux validation boundary

This is a Python-only worker/productization path and is locally verifiable on Linux. No Swift runtime effect is claimed for this slice.
