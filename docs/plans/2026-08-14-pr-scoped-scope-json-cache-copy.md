# PR-scoped scope changed-files cache copy fast path

## Scope

This Python-only performance slice is limited to `scripts/pr_scoped_performance_scope.py` and its changed-files JSON loader used by the PR-scoped performance scope CLI.

## Registered probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-json-read-bytes` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/pr_scoped_performance_scope.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- the probe registry validation tests

## Optimization slice

Keep behavior equivalent while reducing cached changed-files reload overhead. The loader still reads JSON bytes for cold loads, validates that the payload is a list, and protects the cache from caller mutation. Cache hits now copy a cached list directly instead of expanding a cached tuple into a new list.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.

## Acceptance

Accept only if focused tests pass, changed-scope coverage is measurable and at least 95%, the registered local probe shows non-regression or improvement, and the PR-scoped performance CI probe completes successfully.
