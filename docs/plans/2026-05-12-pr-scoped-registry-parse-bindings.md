# PR-scoped registry parse binding slice

## Scope

This slice is a Python-only performance optimization for the PR-scoped performance registry parser in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The parser is on the registered PR-scoped performance path because CI reloads `infra/perf/pr_scoped_probes.json` while selecting and running probe jobs. The change must keep registry semantics unchanged and only reduce repeated global lookups during registry materialization.

## Registered probe

The affected path is covered by `infra/perf/pr_scoped_probes.json` probe `pr-scoped-performance-registry-cache`, which defines focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Verification plan

Run the focused registry-cache tests, changed-scope coverage for the touched files, and the registered local probe on Linux before pushing. The GitHub PR-scoped performance workflow remains the merge gate for the registered probe report.

## Success metric

Accept the slice only if the registered probe shows directionally lower `cold_load_probe_registry_ms_mean` or `build_scope_report_ms_mean` without regressing correctness tests or changed-scope coverage.
