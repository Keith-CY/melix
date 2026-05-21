# PR-scoped definition slots slice

## Scope

This Python-only performance slice targets the PR-scoped performance registry definition objects in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

## Probe coverage

The affected path is already covered by the registered PR-scoped performance probe `pr-scoped-performance-registry-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for registry loading and scope-report construction.

## Optimization

`MetricDefinition` and `ProbeDefinition` are allocated for every parsed registry entry and metric. This slice adds dataclass slots to remove per-instance `__dict__` allocation while preserving frozen dataclass behavior and existing `to_dict()` / `to_scope_dict()` output semantics.

## Verification plan

- Extend the existing registry-cache focused test to assert loaded metric and probe definitions are slotted and still serialize to the same public dictionaries.
- Run the registered `pr-scoped-performance-registry-cache` focused tests.
- Run changed-scope coverage for `pr_scoped_performance.py` and the focused test file.
- Run the registered local probe and compare against `origin/main` using `scripts/pr_scoped_performance_run.py` before pushing.

## Acceptance

Accept only if focused tests pass, changed-scope coverage remains at least 95%, and the registered probe shows lower cold registry-load time without a material cached-load or scope-report regression. The CI registered probe remains the source of truth before merge.
