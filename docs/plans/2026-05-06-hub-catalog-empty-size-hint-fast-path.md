# Hub Catalog Empty Size-Hint Fast Path

## Goal

Avoid redundant regex work when Hub catalog metadata has no model-size hint text.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Linux-Only Constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance Probe

Use the existing registered probe:

- `hub-catalog-tag-normalization-single-pass`

The probe builds a large synthetic Hub catalog page with empty `cardData`, which exercises the hot no-size-hint path.

## Success Metrics

- Focused Hub catalog tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- The local base-vs-head probe reports no behavior drift and ideally lower elapsed time for the empty-card workload.

## Implementation Plan

1. Add an early return to `_size_hint_from_text(...)` for empty text before selecting/searching the regex pattern.
2. Add a focused regression test that proves empty text returns `0` without invoking either compiled regex object.
3. Run focused pytest, changed-scope coverage, `git diff --check`, and the existing local probe before opening the PR.
