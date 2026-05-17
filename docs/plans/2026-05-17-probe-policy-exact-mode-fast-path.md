# Probe Policy Exact Mode Fast Path

## Scope

This Python-only performance slice is limited to `ProbePolicy.from_value` in
`services/mlx-worker-python/worker/productization/probe_policy.py`. The goal is
to reduce hot-path overhead when callers pass already-normalized probe mode
strings such as `"minimal"`, `"off"`, or `"evidence"`.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
fields and measures the no-op policy path plus valid and invalid mode parsing.

## Implementation Plan

1. Keep existing fallback semantics for blank, invalid, non-string, and
   whitespace/case-normalized values.
2. Add an exact string lookup before normalization so supported lowercase values
   reuse the cached policy without calling `strip()` or `lower()`.
3. Add a focused regression assertion that exact supported string values bypass
   normalization.
4. Run the registered focused tests, changed-scope coverage command, and local
   registered probe on Linux before opening the PR.

## Validation Boundary

This slice touches Python-only code and is locally verifiable on Linux. The
hosted PR-scoped performance workflow remains the merge gate for the registered
probe report in CI.
