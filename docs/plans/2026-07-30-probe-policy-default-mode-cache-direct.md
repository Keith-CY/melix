# Probe policy default-mode cache direct lookup

## Scope

This Python-only performance slice is limited to `worker.productization.probe_policy` and the default-policy cache path used by no-value probe mode parsing.

The implementation preserves existing `ProbePolicy.from_env({})` and `ProbePolicy.from_value(None)` behavior while removing duplicate minimal-default branches and routing both paths through the existing `_PROBE_POLICY_BY_DEFAULT_MODE` immutable cache.

No probe policy semantics, telemetry modes, evidence behavior, or Swift runtime behavior change.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`.

The registered entry includes focused `test_command`, `coverage_command`, and `probe_command` coverage for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/probe_policy_noop_overhead_probe.py`

## Verification Plan

Local Linux validation must run:

1. The registered focused probe-policy test command.
2. The registered changed-scope coverage command.
3. The registered `probe-policy-noop-overhead` probe command.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report before merge.

## Success Criteria

Accept the slice only if focused tests pass, changed-scope coverage remains at or above the repository threshold, local registered probe metrics do not regress the measured no-op/default parse paths, and hosted PR-scoped performance CI completes successfully.
