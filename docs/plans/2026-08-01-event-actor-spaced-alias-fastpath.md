# Event extraction common spaced actor alias fast path

## Scope

This Python-only performance slice targets semantic actor field normalization in
`services/mlx-worker-python/worker/productization/event_extraction.py`.

The behavior stays unchanged: common Chinese group-actor aliases such as
`我们`, `双方`, `咱们`, `我俩`, `两人`, and their common single-space forms are
still expanded away before semantic actor matching. Less common punctuation or
spacing variants continue to use the existing normalization fallback.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`event-extraction-group-actor-alias-cache` in `infra/perf/pr_scoped_probes.json`.

That probe declares focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_actor_alias_probe.py`

## Implementation plan

1. Add a small precomputed set for common single-space group-actor aliases.
2. Check that set before the normalized fallback in `_is_group_actor_alias`.
3. Update focused regression assertions so the common spaced aliases no longer
   call `_normalize_similarity_text`.
4. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux before opening the PR.

## Linux verification boundary

This slice changes Python code and is locally verifiable on Linux. No Swift
runtime behavior is changed.
