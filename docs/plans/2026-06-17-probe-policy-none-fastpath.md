# Probe policy `None` parse fast path

## Scope

This Python-only performance slice targets `ProbePolicy.from_value(None)` in
`services/mlx-worker-python/worker/productization/probe_policy.py`. The affected
path is covered by the registered PR-scoped probe `probe-policy-noop-overhead` in
`infra/perf/pr_scoped_probes.json`, including focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Change

Move the `None` guard to the top of `ProbePolicy.from_value` so missing probe
mode values return the cached default policy before string and enum type checks.
This preserves the existing fallback/default semantics while reducing overhead
on the no-op probe-policy path used when a caller passes an absent mode value.

## Verification

- Run the registered focused probe-policy tests.
- Run the registered changed-scope coverage command for the probe-policy scope.
- Run `scripts/probe_policy_noop_overhead_probe.py` locally on Linux and compare
  the `mode_parse_none_call_ms_mean` metric before and after the change.
- Rely on the registered PR-scoped performance workflow in CI for PR validation.
