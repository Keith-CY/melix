# Probe Policy Invalid String Cache

## Goal

Reduce repeated `ProbePolicy.from_value(...)` overhead for unsupported string values while preserving the existing exact lowercase fast path and normalized fallback semantics.

## Slice

This slice is limited to `worker.productization.probe_policy` and the existing registered `probe-policy-noop-overhead` PR-scoped probe. The probe already covers `services/mlx-worker-python/worker/productization/probe_policy.py`, `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`, focused tests, and `scripts/probe_policy_noop_overhead_probe.py` with test, coverage, and probe commands in `infra/perf/pr_scoped_probes.json`.

## Implementation

- Keep exact supported lowercase strings on the direct dictionary lookup path.
- Add a bounded cached helper for non-exact string values so repeated unsupported probe mode values reuse the normalized fallback policy without repeating `strip().lower()`.
- Preserve subclass `str` behavior through the existing normalization branch.

## Verification

Run the registered focused test command, changed-scope coverage command, and `probe-policy-noop-overhead` probe locally on Linux. CI remains the source of truth for the registered PR-scoped performance report.

## 2026-06-13 follow-up: None fast path

`ProbePolicy.from_value(None)` is part of the same fallback contract as empty
probe-mode values. Add a direct `None` branch before the generic non-string
normalization so repeated absent-value parsing returns the cached default policy
without allocating and normalizing `str(None or "")`. The registered probe now
also reports `mode_parse_none_call_ms_mean` alongside the existing empty, valid,
and invalid parse metrics.

## 2026-07-20 follow-up: exact invalid minimal cache

The registered `probe-policy-noop-overhead` probe repeatedly parses the same
exact unsupported lowercase mode string to measure invalid-mode fallback cost.
Keep non-exact string normalization on the existing bounded helper, but add a
small exact-value cache for default-minimal invalid strings after their first
normalization. Repeated exact invalid values can then return the immutable
fallback policy by direct dictionary lookup while preserving the same
`source_value`, fallback mode, and subclass/whitespace normalization behavior.

## 2026-07-26 follow-up: exact debug and common-invalid direct returns

This Python-only slice keeps the same `ProbePolicy.from_value(...)` boundary and
registered `probe-policy-noop-overhead` probe. The exact built-in `str` branch now
returns the common `debug` policy and the common default-minimal invalid policy
before the generic value dictionary lookup. Empty strings, other valid modes,
custom defaults, string subclasses, whitespace normalization, and cached invalid
fallback semantics remain unchanged. Local Linux validation uses the registered
focused tests, changed-scope coverage command, and PR-scoped probe.
