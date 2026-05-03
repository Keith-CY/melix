# Worker runtime stats request counters

## Goal

Optimize the registered Python worker-registry hot path for `WorkerRegistry.runtime_stats()` when many requests are active. The current implementation recomputes active phase and multimodal counters by walking every request on each stats call.

## Scope

This slice is limited to Python worker code that is locally verifiable on Linux:

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`

It does not touch Swift, macOS-only runtime behavior, protocol schemas, generated artifacts, or dependencies.

## Registered probe

The affected path is covered by the PR-scoped probe `worker-registry-resident-bytes-accumulator` in `infra/perf/pr_scoped_probes.json`.

Focused commands from the registry include:

- `test_command` for runtime edge tests and probe registry smoke tests.
- `coverage_command` with `scripts/changed_scope_coverage.py` for the changed worker-registry scope.
- `probe_command` via `scripts/worker_registry_resident_probe.py`, reporting `elapsed_ms_mean` and `request_stats_elapsed_ms_mean`.

## Approach

Maintain active request, prefill, decode, and multimodal request counters alongside `_requests`. Update those counters only when requests start, change phase, or finish. `runtime_stats()` can then read counters directly instead of scanning all active requests.

## Success metrics

- Behavior parity for request lifecycle counters.
- Changed-scope coverage remains at or above 95%.
- Registered local probe shows lower `request_stats_elapsed_ms_mean` versus the origin/main baseline.

## Local result

Accepted for PR: the Linux registered probe reduced `request_stats_elapsed_ms_mean` from `0.351907` ms on the origin/main baseline to `0.015067` ms after the change (`-0.336840` ms, `23.356x`, `95.72%` improvement). Overall resident loop `elapsed_ms_mean` moved from `0.027591` ms to `0.029940` ms; this probe metric covers a separate load/unload path and is effectively unchanged for this request-counter slice.
