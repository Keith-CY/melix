# Probe Policy Empty Default Cache Slice

## Goal

Avoid allocating a new `ProbePolicy` instance on the hot empty/default probe-mode
path while preserving the existing distinction between an unset source value and
an explicit lower-case mode string.

## Scope

- `services/mlx-worker-python/worker/productization/probe_policy.py`
- `services/mlx-worker-python/worker/productization/probe_policy_overhead.py`
- `services/mlx-worker-python/tests/test_probe_policy.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The entry has
focused `test_command`, `coverage_command`, and `probe_command` values. This
slice extends the probe payload with the empty/default parse metric because that
is the directly optimized path; the registry metric gate remains scoped to the
pre-existing stable no-op overhead metrics so base/head comparisons remain
comparable on `origin/main`.

## Plan

1. Add a cached policy lookup for empty/unset values keyed by default mode.
2. Keep explicit string modes mapped to the existing source-preserving cached
   policies.
3. Add regression coverage proving empty/default calls reuse cached policy
   objects without changing source/fallback semantics.
4. Extend the local/CI probe to report `mode_parse_empty_call_ms_mean`.
5. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux before opening the PR.

## Acceptance

- Empty/default probe-mode parsing returns a cached policy object.
- Explicit mode parsing and invalid fallback behavior remain unchanged.
- Focused test and changed-scope coverage commands pass.
- Registered probe shows the optimized empty/default metric and passes the
  threshold gate.
