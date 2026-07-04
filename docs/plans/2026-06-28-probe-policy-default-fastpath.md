# Probe policy default-mode fast path

## Scope

This Python-only performance slice is limited to `worker.productization.probe_policy.ProbePolicy.from_value(...)` and `ProbePolicy.from_env(...)` when callers use the default `ProbeMode.MINIMAL` and pass empty, missing, or `None` probe-mode inputs.

The behavior contract stays unchanged:

- empty environment mappings still resolve to the default policy;
- missing `MELIX_PROBE_MODE` values still resolve to the default policy;
- `None` and empty string values still resolve to the default policy;
- non-minimal default modes still use the existing default-mode policy map;
- valid, normalized, and invalid probe-mode parsing semantics are unchanged.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`.

The probe entry has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/probe_policy_noop_overhead_probe.py`

This slice uses the existing `mode_parse_empty_call_ms_mean`, `mode_parse_none_call_ms_mean`, and `env_parse_empty_call_ms_mean` metrics as the primary local/CI performance evidence.

## Implementation plan

1. Keep focused probe-policy tests unchanged as behavior guards.
2. Bind the minimal default `ProbePolicy` singleton at module load time.
3. Return that singleton directly on the default-mode empty/none/env-missing paths, avoiding repeated default-mode dictionary lookups in the common no-configuration hot path.
4. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused probe-policy tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement on default-mode empty/none/env-empty metrics.
- Hosted `probe-policy-noop-overhead` PR-scoped CI completes successfully before merge.
