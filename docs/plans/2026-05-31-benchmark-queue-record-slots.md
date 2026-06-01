# Benchmark queue record slots

## Scope

This Python performance slice is limited to `services/mlx-worker-python/worker/productization/benchmark_queue.py`, specifically the in-memory queue record objects created while listing benchmark queue JSON files.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `benchmark-queue-decoded-record-cache` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values for the benchmark queue store and probe dispatch path.

## Change

`BenchmarkQueueRecord` and its private cache entry use frozen dataclasses. The queue listing hot path can construct and cache many records, then clone records again at the public return boundary. This slice keeps the same fields and immutability behavior while adding dataclass slots so each record/cache entry avoids an instance `__dict__` allocation.

## Verification

Run the registered focused tests, changed-scope coverage, and `benchmark-queue-decoded-record-cache` probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
