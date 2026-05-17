# Probe policy string fast path

## Scope

This Python-only performance slice keeps `ProbePolicy.from_value(...)` behavior unchanged while reusing immutable policy instances for supported probe modes.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused entries for:

- `test_command`: probe-policy unit coverage and registry dispatch checks.
- `coverage_command`: changed-scope coverage over `probe_policy.py`, `probe_policy_overhead.py`, focused tests, and the probe script.
- `probe_command`: command-json execution of `scripts/probe_policy_noop_overhead_probe.py`.

## Implementation plan

1. Add focused regression coverage showing exact lowercase valid and invalid strings preserve the same source-value and fallback semantics.
2. Keep the existing `ProbeMode` object fast path.
3. Reuse immutable cached `ProbePolicy` instances for supported modes after normalization while preserving fallback construction for invalid values.
4. Run focused pytest, changed-scope coverage, and the registered probe locally on Linux.
5. Use PR-scoped performance CI as the final registered probe gate before merge.

## Validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime performance claim is made.
