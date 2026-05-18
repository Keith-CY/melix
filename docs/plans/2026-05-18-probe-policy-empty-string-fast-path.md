# Probe Policy Empty String Fast Path

## Scope

This Python-only performance slice is limited to `ProbePolicy.from_value` in
`services/mlx-worker-python/worker/productization/probe_policy.py`. The targeted
hot path is the explicit empty-string parse used by no-op probe policy checks
and by synthetic overhead measurement.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The registry
entry already includes focused `test_command`, `coverage_command`, and
`probe_command` values covering:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `scripts/probe_policy_noop_overhead_probe.py`

The probe reports `mode_parse_empty_call_ms_mean`, along with the existing no-op
recorder and policy overhead metrics.

## Implementation Plan

1. Keep behavior identical for supported modes, whitespace-normalized strings,
   invalid values, non-strings, and explicit default modes.
2. Add a direct exact-empty-string return before dictionary lookup and
   normalization in `ProbePolicy.from_value`.
3. Verify with the focused registered tests, changed-scope coverage, and the
   registered probe locally on Linux.
4. Use the PR-scoped performance workflow as the merge gate after opening the PR.

## Acceptance Criteria

- Focused tests pass.
- Changed-scope coverage for touched Python/test/probe paths is at least 95%.
- Local registered probe shows lower `mode_parse_empty_call_ms_mean` compared
  with `origin/main` without regressing probe threshold pass status.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
