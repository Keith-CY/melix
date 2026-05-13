# Probe Policy Mode Check Fast Path

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/productization/probe_policy.py` and its
focused tests. It keeps probe mode semantics unchanged while avoiding per-call
temporary set allocation and repeated enum comparisons in the hot
`telemetry_enabled` and `evidence_enabled` properties.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The probe has
focused `test_command`, `coverage_command`, and `probe_command` entries and
reports:

- `no_op_policy_check_call_ms_mean`
- `no_op_policy_check_overhead_pct`
- `no_op_recorder_overhead_pct`
- `threshold_passed`

## Verification plan

1. Run the focused probe policy tests and PR-scoped performance registry tests on
   Linux.
2. Run changed-scope coverage for the touched probe policy files and tests.
3. Run the registered `probe-policy-noop-overhead` probe locally, then use the
   GitHub PR-scoped performance workflow as the merge gate.

## Success criteria

- Probe policy behavior remains identical for all supported modes.
- Changed-scope coverage remains at least 95%.
- The local registered probe and CI registered probe show a clear non-regression
  or improvement in policy-check overhead with `threshold_passed == 1.0`.