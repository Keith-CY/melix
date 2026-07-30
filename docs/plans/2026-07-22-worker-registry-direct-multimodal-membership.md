# Worker registry direct multimodal membership fast path

## Scope

This Python performance slice is limited to request counter updates in
`services/mlx-worker-python/worker/registry.py`. It preserves the existing
multimodal runtime-kind classification while removing the helper method call from
the request start, phase replacement, and finish hot paths.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`worker-registry-resident-bytes-accumulator` in
`infra/perf/pr_scoped_probes.json`. The probe watches:

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/worker_registry_resident_probe.py`

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. The probe reports model load/unload resident-byte timing,
loaded-model listing cache timing, request-counter stats timing, and request
lifecycle timing.

## Slice

Inline membership checks against the module-level `_MULTIMODAL_REQUEST_KINDS`
frozenset inside `_add_request_to_counters()` and
`_remove_request_from_counters()`. The public/static helper remains available for
callers and tests, but the counter mutation hot path no longer pays a method call
for every request lifecycle transition.

## Verification

Run the registered focused tests, changed-scope coverage command, and local
registered probe before opening the PR. Use GitHub Actions PR-scoped performance
as the final base-vs-head registered probe validation and merge gate.
