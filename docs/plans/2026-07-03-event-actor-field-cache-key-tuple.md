# Event Actor Field Cache Key Tuple Copy Slice

## Scope

This Python-only performance slice is limited to
`worker.productization.event_extraction._event_field_cache_key()`, which runs on
semantic actor-field extraction before the cached group-actor alias expansion.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`event-extraction-group-actor-alias-cache` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_actor_alias_probe.py`

## Implementation plan

1. Preserve validation semantics for actor field values: `None` maps to an empty
   cache key, non-list values fail, and non-string list items fail.
2. After validation, materialize the cache key with `tuple(value)` instead of a
   Python-level append loop. This keeps the same immutable cache key while moving
   the copy to CPython's tuple constructor.
3. Run the registered focused tests, changed-scope coverage, and the registered
   probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the
   PR.

## Metrics

The registered probe reports `elapsed_ms_mean`, `normalize_calls_mean`, and
`peak_bytes_mean`. Local Linux probe output is recorded in the PR; GitHub Actions
remains the authoritative registered probe report before merge.
