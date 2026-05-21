# Runtime Kwarg Accepts Inline Membership Slice

## Scope

This slice targets the Python runtime helper path in
`services/mlx-worker-python/worker/runtime/runtime_utils.py`.

The affected path is already covered by the registered PR-scoped probe
`runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`, with
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Change

Inline the `CallableKwargSignature` membership checks used by
`callable_declares_kwarg` and `callable_accepts_kwarg`. The cached signature
lookup remains unchanged; the hot path avoids an additional bound method call on
every keyword acceptance check.

## Verification Plan

- Run the registered focused runtime-utils tests through the probe registry
  command.
- Run changed-scope coverage for the registered runtime-utils probe.
- Run `scripts/runtime_utils_kwarg_cache_probe.py` locally on Linux before and
after the change and compare `elapsed_ms_mean` and
  `inspect_signature_calls_mean`.

## Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
