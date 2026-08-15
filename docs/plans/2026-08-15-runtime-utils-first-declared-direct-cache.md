# Runtime utils first-declared kwarg direct cache

## Scope

This Python-only performance slice is limited to `first_declared_kwarg(...)` in
`services/mlx-worker-python/worker/runtime/runtime_utils.py`.

The change keeps callable keyword introspection semantics unchanged while adding
a direct LRU cache for repeated `(callable, bound-method-skip, keywords)` lookups.
It does not change the lower-level callable signature cache, package version
cache, or model weight byte estimation paths.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry defines focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `scripts/runtime_utils_kwarg_cache_probe.py`

## Measurement plan

Run the registered focused tests, changed-scope coverage command, and the
runtime-utils kwarg probe locally on Linux before PR creation. The probe script
emits `first_declared_elapsed_ms_mean` and
`first_declared_signature_calls_mean`; elapsed time is lower-is-better and
signature-call count should remain unchanged. The existing registry entry is
used as-is to keep this behavior slice scoped to the runtime utility change.

## Acceptance

Accept the slice only if behavior tests pass, changed-scope coverage remains at
or above repository policy for touched lines, local probe output shows a clear
first-declared latency improvement without increasing signature calls, and the
PR-scoped performance CI probe completes successfully.
