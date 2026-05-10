# Worker Registry Sparse Model Spec Fast Path

## Context

`WorkerRegistry.load_model` resolves every requested `ModelSpec` through
`_is_sparse_model_request` before deciding whether to replace a sparse request
with the catalog entry. The PR-scoped worker registry probe exercises this path
inside a preloaded model churn loop, so the sparse check should avoid generic
protobuf field enumeration when possible.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`worker-registry-resident-bytes-accumulator` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes:

- `watch_globs` covering `services/mlx-worker-python/worker/registry.py`, the
  focused runtime-edge tests, the PR-scoped performance tests, and
  `scripts/worker_registry_resident_probe.py`.
- `test_command` for worker registry sparse request, resident-byte, sorted
  listing, request-counter, runtime-service, and probe-selection tests.
- `coverage_command` for the changed worker registry scope.
- `probe_command` via `scripts/worker_registry_resident_probe.py` reporting
  model load/unload latency, listing latency, sort calls, request stats latency,
  and resident bytes.

## Slice

Replace the sparse `ModelSpec` check's `ListFields()` allocation with direct
field-default checks for the known `ModelSpec` fields. Preserve the existing
semantics: an empty spec or `model_id`-only spec is sparse; any other populated
field makes the request non-sparse.

## Verification

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Compare the probe against an `origin/main`
baseline worktree before accepting the slice.
