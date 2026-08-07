# Worker registry counter decrement fast path

## Scope

This Python performance slice is limited to request counter decrement handling in
`services/mlx-worker-python/worker/registry.py`. It preserves the existing
non-negative guard behavior while avoiding repeated `max()` calls on the hot path
used by request finish, phase replacement, and lease replacement flows.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`worker-registry-resident-bytes-accumulator` in
`infra/perf/pr_scoped_probes.json`. The probe watches:

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/worker_registry_resident_probe.py`

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. The probe reports resident-byte load/unload timing,
loaded-model listing cache timing, request counter stats timing, and request
lifecycle counter timing.

## Slice

Replace the saturated decrement expression `max(0, counter - 1)` with explicit
positive checks before decrementing the relevant active request counters. This
keeps defensive underflow protection for unexpected private helper use while
reducing function-call overhead in the common balanced counter path.

## Verification

Run the registered focused tests, changed-scope coverage command, and local
registered probe before opening the PR. Use the PR-scoped performance workflow as
the merge gate for base-vs-head probe validation.
