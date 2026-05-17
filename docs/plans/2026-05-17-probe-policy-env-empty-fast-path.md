# Probe Policy Empty Environment Fast Path

## Scope

This Python-only performance slice is limited to `ProbePolicy.from_env(...)` in
`services/mlx-worker-python/worker/productization/probe_policy.py` and the
registered no-op probe-policy overhead measurement path.

The common production default path has no `MELIX_PROBE_MODE` value set. Before
this slice, `from_env({})` still delegated through `from_value("")`, adding an
extra classmethod call on the no-env hot path even though the default policy is a
cached singleton.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. That entry
already includes focused `test_command`, `coverage_command`, and
`probe_command` fields for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `scripts/probe_policy_noop_overhead_probe.py`

This slice extends the probe metrics with `env_parse_empty_call_ms_mean` so the
registered local and CI probe report measures the optimized path directly. The
probe also reports `mode_parse_empty_call_ms_mean` alongside the existing valid
and invalid parse metrics, and the empty-env probe sample reuses a preallocated
empty mapping so the metric isolates `from_env(...)` rather than per-iteration
dictionary allocation.

## Implementation Plan

1. Preserve existing behavior for valid, invalid, whitespace-normalized, and
   explicit default-mode inputs.
2. Return the cached default-mode policy directly when `from_env(...)` sees a
   missing or falsey `MELIX_PROBE_MODE` value.
3. Add focused regression assertions for empty env maps, explicit falsey env
   values, and non-minimal default modes.
4. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux before opening the PR.
5. Use the GitHub Actions PR-scoped performance workflow as the final merge gate.

## Validation Boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance claim is made.
