# Rerank Core Registry Binding Performance Slice

## Scope

This Python-only performance slice is limited to `RerankCore.rerank()` in
`services/mlx-worker-python/worker/engine/rerank_core.py`.

The hot path repeatedly touches `self._registry` while servicing rerank requests.
This slice binds the registry to a local variable once per request and reuses that
local for loaded-model lookup and rerank runtime dispatch. Ranking behavior,
request document passthrough, and response construction stay unchanged.

## Registered Probe

Reuse registered PR-scoped probe `rerank-core-top-k-heap-selection` in
`infra/perf/pr_scoped_probes.json`. The probe already has focused
`test_command`, `coverage_command`, and `probe_command` entries for the affected
rerank core path.

This slice also registers the probe's existing `request_elapsed_ms` output as a
lower-is-better metric so CI can validate the request dispatch path touched by
this local-binding change, not only the bounded top-k ranker loop.

## Verification Plan

1. Run the focused rerank tests and probe-selection tests from the registered
   probe command.
2. Run changed-scope coverage for `rerank_core.py`, `test_rerank_runtime.py`,
   `test_pr_scoped_performance.py`, and `scripts/rerank_top_k_probe.py`.
3. Run the registered probe locally on Linux before and after the slice and
   compare `request_elapsed_ms` plus the existing top-k metrics.
4. Use the PR-scoped performance workflow as the merge gate for the registered
   probe report.

## Acceptance

Accept only if behavior tests pass, changed-scope coverage remains at or above
95%, and the registered probe shows non-regressing or improved
`request_elapsed_ms` while preserving ranker metrics and document passthrough
counters.
