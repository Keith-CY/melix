# Benchmark queue parameter copy fast path

## Scope

This Python performance slice is limited to `BenchmarkQueueStore` record cloning
and JSON-decoded parameter normalization in
`services/mlx-worker-python/worker/productization/benchmark_queue.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`benchmark-queue-decoded-record-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the benchmark queue store, probe dispatch, and
changed-scope coverage.

## Plan

Persisted benchmark queue records normally carry an already-string
`parameters` mapping, and public return cloning repeatedly copies the same
mapping for warm-cache list calls. Use direct `dict.copy()` on known dictionaries
instead of the generic `dict(mapping)` constructor. This keeps the defensive copy
boundary intact while reducing per-record clone overhead.

## Verification

Run the registered focused tests, changed-scope coverage, and the registered
benchmark queue probe locally on Linux before pushing. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe report.
