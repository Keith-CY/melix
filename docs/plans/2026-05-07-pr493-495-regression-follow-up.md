# PR 493 and PR 495 Regression Follow-up

## Goal

Address the post-merge PR-scoped performance reports for PR 493 and PR 495 with a narrow follow-up that improves the changed hot paths without touching the performance registry.

## Context

The original reports included broad regressions because the earlier PRs changed `infra/perf/pr_scoped_probes.json`, which force-selected the full probe registry. Current `main` already contains follow-up performance work for several unrelated probes, so this slice stays scoped to the two runtime paths introduced by PR 493 and PR 495:

- event-extraction group actor alias expansion
- training-dataset automatic validation split materialization

## Scope

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `scripts/event_extraction_actor_alias_probe.py`
- Focused tests for the two behavior contracts

## Optimization Plan

1. Keep the `heapq.nsmallest(...)` validation-index selection from PR 495, then build train and validation outputs in one pass over the source samples.
2. Keep the cached normalized group-actor alias set from PR 493, then combine actor-field deduplication, alias expansion, and expanded-value deduplication into one actor-specific scan.
3. Keep the actor-alias probe's small smoke workload on punctuation-normalized aliases, and keep the default workload mixed with sparse punctuation-normalized aliases so hosted metrics show reduced normalization without reporting a fully elided fallback path.
4. Preserve output ordering, digest inputs, and existing semantic scoring behavior.
5. Verify with focused pytest, changed-scope coverage, and local command-json probes for the two optimized paths.

## Success Metrics

- Focused pytest for training dataset split and event actor alias behavior passes.
- Changed-line coverage for the follow-up diff is at least 95 percent.
- Local probes report stable structural metrics and improved or comparable elapsed time for the optimized paths.
- `git diff --check` passes.
