# Request state slots lifecycle slice

## Scope

This Python-only performance slice is limited to `RequestState`, the small per-request state object used by `WorkerRegistry.start_request`, request leases, phase changes, and request lifecycle cleanup.

## Registered probe

The affected path is covered by the registered PR-scoped probe `worker-registry-resident-bytes-accumulator` in `infra/perf/pr_scoped_probes.json`. This slice extends that probe's `watch_globs`, focused `test_command`, and `coverage_command` to include `services/mlx-worker-python/worker/engine/request_state.py` and the slot-regression test, while retaining the existing local `scripts/worker_registry_resident_probe.py` workload.

## Optimization

Reduce request lifecycle overhead in the worker registry by keeping the per-request state compact and avoiding full counter remove/add churn during phase-only transitions. `RequestState` uses `@dataclass(slots=True)` so high-churn lifecycle paths avoid allocating a per-instance `__dict__`, and `WorkerRegistry.set_request_phase(...)` now updates only the prefill/decode counters that can change when a request keeps the same identity and runtime kind. The behavior remains unchanged: request id, runtime kind, phase, cancel event, sequence allocation, token append, assistant text materialization, active-request counts, and multimodal counters retain the same values.

## Verification plan

1. Run the focused registered worker-registry test command locally on Linux.
2. Run changed-scope coverage through the registered coverage command.
3. Run the registered `worker-registry-resident-bytes-accumulator` probe locally against `origin/main` and this branch, then compare `request_lifecycle_elapsed_ms_mean` plus the existing registry metrics.
4. Let PR-scoped performance CI validate the registered probe before merge.

## Acceptance

- Focused tests and changed-scope coverage pass.
- The registered probe shows a clear request-lifecycle improvement or a defensible neutral effect without regressing the broader registry metrics.
- PR-scoped performance CI completes successfully before merge.
