# Runtime utils declares-kwarg cache

## Goal

Reduce hot-loop overhead for repeated `callable_declares_kwarg(...)` checks in the Python runtime utility layer without changing introspection semantics.

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/runtime/runtime_utils.py` and its focused runtime utility tests/probe support. It adds a cached boolean lookup for explicit keyword declaration checks, parallel to the existing `callable_accepts_kwarg(...)` cache, while preserving the unhashable-callable fallback path.

A 2026-08-14 follow-up slice keeps the same registered probe boundary and optimizes `first_declared_kwarg(...)` by reading the cached `keyword_accessible_params` set once and using direct membership checks inside the candidate loop. It preserves variadic-kwargs behavior because only explicitly declared keyword-accessible parameters are eligible.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`. This slice extends the probe script and registry metrics so the existing focused `test_command`, `coverage_command`, and `probe_command` also report declaration-cache metrics:

- `declares_elapsed_ms_mean` (lower is better)
- `declares_signature_calls_mean` (lower is better)

The 2026-08-14 follow-up keeps the same registered probe entry and extends the checked probe script with supplemental first-declared lookup metrics for local and CI evidence:

- `first_declared_elapsed_ms_mean` (lower is better)
- `first_declared_signature_calls_mean` (lower is better)

The registered probe continues to report the existing accept-cache metrics:

- `elapsed_ms_mean`
- `inspect_signature_calls_mean`

## Verification plan

- Run the focused runtime utility and PR-scoped performance tests.
- Run changed-scope coverage for the touched Python/probe files and require at least 95% changed-line coverage.
- Run the registered `runtime-utils-kwarg-signature-cache` probe locally on Linux against `origin/main` and this branch via `scripts/pr_scoped_performance_run.py`.
- Use the GitHub PR-scoped performance workflow as the merge gate after opening the PR.

## Success criteria

- Runtime utility tests prove explicit declaration semantics and cache clearing behavior remain unchanged.
- Probe metrics show declaration checks still inspect the callable signature once per sample and improve or do not regress the registered probe on Linux.
- CI PR-scoped performance completes successfully before merge.
