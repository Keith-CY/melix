# Worker registry request counter local-bind slice

## Scope

This Python-only performance slice is limited to the `WorkerRegistry` request
counter helpers in `services/mlx-worker-python/worker/registry.py`.

The hot path updates request counters on every request start, phase transition,
lease release, and finish. The helpers previously re-read `RequestState.phase`
and `RequestState.runtime_kind` across several branch checks and used nested
counter guard branches in the decrement path.

This slice keeps counter semantics unchanged while binding `phase` and
`runtime_kind` once per helper call and flattening guarded decrement checks.
No request lifecycle behavior, model lease handling, runtime-stat field, or
observability schema changes.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `worker-registry-resident-bytes-accumulator` in
`infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`,
`coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_runtime_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/worker_registry_resident_probe.py`

## Verification plan

Run on Linux before push:

1. Focused registered tests for the worker registry probe.
2. Registered changed-scope coverage command.
3. Registered probe command, comparing the pre-change and post-change JSON
   metrics from `scripts/worker_registry_resident_probe.py`.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the final registered probe gate
before merge.

## Local metrics

Initial local baseline from `origin/main`:

```json
{"elapsed_ms_mean": 0.012907, "loaded_model_listing_elapsed_ms_mean": 0.055105, "loaded_model_listing_sort_calls_mean": 1.0, "loop_count": 250.0, "preloaded_model_count": 2000.0, "request_count": 3000.0, "request_lifecycle_elapsed_ms_mean": 0.004124, "request_stats_elapsed_ms_mean": 0.003933, "resident_bytes_mean": 8196096.0, "sample_count": 3.0}
```

Final post-change local registered-probe sample:

```json
{"elapsed_ms_mean": 0.011868, "loaded_model_listing_elapsed_ms_mean": 0.054322, "loaded_model_listing_sort_calls_mean": 1.0, "loop_count": 250.0, "preloaded_model_count": 2000.0, "request_count": 3000.0, "request_lifecycle_elapsed_ms_mean": 0.004161, "request_stats_elapsed_ms_mean": 0.00392, "resident_bytes_mean": 8196096.0, "sample_count": 3.0}
```

This local sample shows the primary load/unload resident-byte loop improving by
0.001039 ms per loop (about 8.0%) and the request-stats loop improving by
0.000013 ms per call (about 0.3%). The request lifecycle loop moved by 0.000037
ms per request (about 0.9%) in the slower direction, below the registered
absolute warning tolerance; CI remains the authoritative registered probe
validation.
