# PR-scoped Direct Probe Disjoint Fast Path

## Summary

Optimize the Python PR-scoped performance scope matcher by avoiding the direct
force-all probe scan when the normalized changed-path set is disjoint from the
small set of exact direct force-all paths.

## Scope

- Affected path: `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
- Registered probe: `pr-scoped-performance-scope-matcher` in
  `infra/perf/pr_scoped_probes.json`.
- Verification remains Linux-local for Python tests, changed-scope coverage, and
  the registered probe.

## Behavior and Metrics

Behavior is unchanged: direct force-all probe IDs are still added whenever one of
the registered exact direct paths is present. The fast path only skips the helper
call for common changed-file sets that do not contain those exact paths.

Success metric: lower or neutral `build_scope_report_ms_mean` from the registered
`pr-scoped-performance-scope-matcher` probe, with unchanged selected probe count
and force-all state.
