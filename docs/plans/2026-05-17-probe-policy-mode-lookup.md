# Probe Policy Mode Lookup Slice

## Scope

This Python-only performance slice is limited to the `ProbePolicy.from_value(...)`
mode parser in `services/mlx-worker-python/worker/productization/probe_policy.py`
and the existing registered PR-scoped probe `probe-policy-noop-overhead`.

## Registered Probe Coverage

The affected path is covered by `infra/perf/pr_scoped_probes.json` entry
`probe-policy-noop-overhead`. The entry already includes focused
`test_command`, `coverage_command`, and `probe_command` coverage for:

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `scripts/probe_policy_noop_overhead_probe.py`

This slice extends the same registered probe metrics with parser timing for
valid and invalid `MELIX_PROBE_MODE` values so the CI report validates the parser
fast path directly, not only the no-op recorder/property access path.

## Optimization

Replace the exception-driven `ProbeMode(raw_value)` parser in
`ProbePolicy.from_value(...)` with a module-level value-to-mode lookup table.
This preserves the existing semantics:

- `ProbeMode` instances are returned directly with their source value.
- Empty or missing values use the configured default mode.
- Recognized strings still accept surrounding whitespace and case-insensitive
  values.
- Non-empty unrecognized values still fall back to the default mode and set
  `fallback_applied=True` with the normalized source value.

The expected win is largest for invalid mode values because the production-safe
fallback path no longer allocates and catches a `ValueError`.

## Verification Plan

1. Run the focused `probe-policy-noop-overhead` pytest command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered `probe-policy-noop-overhead` probe locally on Linux before
   and after the code change, comparing the new `mode_parse_*_ms_mean` metrics
   and existing no-op overhead metrics.
4. Let GitHub Actions run the registered PR-scoped performance workflow and use
   that report as merge evidence.

## Local Baseline

Before this slice, an ad-hoc parser microbenchmark on Linux reported:

```json
{"invalid_parse_ms_mean": 0.003595027, "mode_instance_parse_ms_mean": 0.001438234, "valid_debug_parse_ms_mean": 0.001768983}
```

The registered probe did not yet include parser-specific metrics, so this plan
records the ad-hoc baseline and extends the registered probe for the PR and CI
report.
