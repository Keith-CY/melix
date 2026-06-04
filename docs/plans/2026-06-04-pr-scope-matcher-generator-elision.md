# PR Scope Matcher Generator Elision

## Slice

Elide generator-expression allocation in the PR-scoped performance scope matcher wildcard helpers while preserving the existing exact/wildcard matching semantics.

## Registered Probe

The affected path is covered by `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/pr_scoped_performance.py` and the paired tests.

## Implementation Plan

1. Keep the change limited to the wildcard matcher helpers in `pr_scoped_performance.py`.
2. Replace generator-based `any(...)` calls with explicit early-return loops and local helper bindings to avoid per-call generator allocation on large changed-file sets.
3. Add a regression test proving force-all wildcard matching still short-circuits once a match is found.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before pushing.

## Validation Boundary

This is a Python-only slice and is locally verifiable on Linux. CI remains the source of truth for the full PR-scoped performance report against the branch and base commit.
