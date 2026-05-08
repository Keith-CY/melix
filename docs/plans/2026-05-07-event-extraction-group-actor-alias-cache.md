# Event Extraction Group Actor Alias Cache

## Goal

Avoid rebuilding the normalized group-actor alias set for every semantic actor value during event-extraction scoring.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it is verifiable on Linux with focused pytest, changed-scope coverage, and a local command-json performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_actor_alias_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Register `event-extraction-group-actor-alias-cache` in PR-scoped performance CI. The probe repeatedly expands semantic actor values containing group aliases and non-aliases, reports elapsed time and structural normalize-call counts, and compares `origin/main` to the PR branch. The May 7 follow-up slice keeps the same registered probe and extends the cache boundary from the static alias set to repeated actor-value expansion for identical normalized actor tuples. The May 8 follow-up keeps the same behavior and registered probe while adding a bounded cache to `_is_group_actor_alias(...)` so repeated group-alias checks across different actor tuples avoid rescanning the same strings.

## Success metrics

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe emits concrete metrics and shows fewer repeated alias-normalization calls on the branch for repeated actor-value expansion.
- Hosted `pr-scoped-performance` validates the registered probe before merge.
