# Event actor alias local bindings slice

## Scope

Optimize the Python event-extraction semantic actor expansion hot path covered by
the registered `event-extraction-group-actor-alias-cache` PR-scoped performance
probe.

Affected code:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- focused behavior/probe coverage in `services/mlx-worker-python/tests/test_event_extraction.py`
  and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- registered probe script `scripts/event_extraction_actor_alias_probe.py`

## Current behavior

`_semantic_field_values("actor", ...)` normalizes and deduplicates actor field
values, then expands group actor aliases such as `我们`, `双方`, and normalized
variants into the two speaker slots. `_expanded_semantic_actor_values()` is cached
by the normalized tuple, but cache misses still perform repeated global method
lookups while populating the expanded list.

## Optimization

Bind the group-alias predicate and collection mutator methods once per
`_expanded_semantic_actor_values()` cache miss, and inline the two speaker-slot
expansion instead of allocating a short `expansion` tuple for every input value.
This keeps actor expansion semantics unchanged while reducing repeated global,
attribute lookup, and tiny tuple allocation overhead inside the value-expansion
loop.

## Probe and success metric

Registered probe: `event-extraction-group-actor-alias-cache` in
`infra/perf/pr_scoped_probes.json`.

Success metric:

- `elapsed_ms_mean` lower is better.
- `normalize_calls_mean`, `output_length_per_sample`, and `value_count` must stay
  semantically stable for the compared workload.

## Verification plan

1. Run focused event-extraction and PR-scoped probe tests.
2. Run changed-scope coverage with `scripts/changed_scope_coverage.py`; changed
   scope must remain at least 95% covered.
3. Run the registered local probe on Linux.
4. Compare baseline and optimized probe runs on the same synthetic workload.
5. Let GitHub Actions run the registered PR-scoped performance workflow before
   merging.

## Validation boundary

This slice is Python-only and locally validated on Linux. It claims no Swift
runtime effect.
