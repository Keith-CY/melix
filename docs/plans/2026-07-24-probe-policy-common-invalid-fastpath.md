# Probe policy common invalid-mode fast path

## Scope

This Python-only performance slice is limited to repeated parsing of the common
invalid probe-mode sentinel `definitely-not-valid` in
`worker.productization.probe_policy.ProbePolicy.from_value(...)`.

The behavior contract stays unchanged: the invalid value still falls back to the
requested default mode, keeps `source_value` normalized to `definitely-not-valid`,
and marks `fallback_applied=True`. Other invalid values, valid values, empty
values, and non-minimal default-mode parsing keep the existing behavior.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`.

The probe entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/probe_policy_noop_overhead_probe.py`

This slice uses `mode_parse_invalid_call_ms_mean` as the primary performance
metric because the registered probe repeatedly parses `definitely-not-valid`.

## Implementation plan

1. Keep the existing focused probe-policy behavior tests as guards.
2. Add a cached immutable policy for the common invalid minimal-mode sentinel.
3. Return that cached policy from both exact lowercase and normalized string
   paths before falling through to the generic invalid-value LRU.
4. Run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused probe-policy tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports a directionally lower `mode_parse_invalid_call_ms_mean`
  locally and in CI without introducing gated regressions.
- Hosted `probe-policy-noop-overhead` PR-scoped CI completes successfully before merge.