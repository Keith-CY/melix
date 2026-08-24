# Rerank top-1 max/index selection

## Scope

This Python-only performance slice is limited to `RerankCore._rank_scores(...)`
when `top_k == 1` in `services/mlx-worker-python/worker/engine/rerank_core.py`.
The behavior contract remains unchanged: select the highest score and preserve
the earliest document index when scores tie.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `rerank-core-top-k-heap-selection` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for the rerank core path, focused tests, and
`scripts/rerank_top_k_probe.py`.

## Implementation plan

- Keep the bounded `top_k > 1` heap path unchanged.
- Replace the Python-level top-1 manual scan with `max(scores)` followed by
  `scores.index(best_score)`, using CPython's list loops for the common top-1
  probe workload.
- Preserve tie behavior because `list.index(...)` returns the first matching
  score after `max(...)` identifies the winning value.

## Verification

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux. Compare the registered probe against an `origin/main`
baseline before pushing. GitHub Actions PR-scoped performance remains the merge
gate.
