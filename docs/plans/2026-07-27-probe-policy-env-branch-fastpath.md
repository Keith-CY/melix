# Probe policy environment branch fast path

## Scope

This Python-only performance slice is limited to `ProbePolicy.from_env(...)` in
`services/mlx-worker-python/worker/productization/probe_policy.py`.

The change preserves probe-mode parsing behavior while splitting the empty
explicit mapping path from the ambient `os.environ` path. Empty mappings are a
hot no-op path in probe-policy checks and should return the cached default
policy without evaluating the conditional expression that also handles ambient
environment lookup.

## Registered probe

The affected path is covered by the existing `probe-policy-noop-overhead`
registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.
That entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and reports the `env_parse_empty_call_ms_mean` metric for
this slice.

## Implementation plan

1. Keep `ProbePolicy.from_env` behavior unchanged for empty explicit mappings,
   ambient `os.environ`, missing `MELIX_PROBE_MODE`, valid modes, and invalid
   fallback values.
2. Split the `env is not None` branch so the empty mapping path returns before
   choosing between `os.environ` and the supplied mapping.
3. Re-run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Linux verification boundary

This slice only changes Python code and is locally verifiable on Linux. CI still
provides the authoritative base-vs-head registered probe report before merge.
