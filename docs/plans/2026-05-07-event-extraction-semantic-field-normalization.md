# Event Extraction Semantic Field Normalization Slice

## Scope

This slice keeps event-extraction scoring semantics unchanged while narrowing the
hot path in `worker.productization.event_extraction._semantic_field_values`.
Semantic scoring repeatedly normalizes event field arrays and removes duplicate
values before optional actor-alias expansion. The previous path built one
intermediate normalized list and then a second de-duplicated list.

## Optimization

Normalize, discard blanks, validate item types, and preserve first-seen unique
values in a single pass for semantic field scoring. Actor fields still use the
existing cached group-actor alias expansion after the normalized unique value
list is produced.

## Probe

The affected path is covered by the registered PR-scoped probe
`event-extraction-group-actor-alias-cache` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused tests, coverage,
and `scripts/event_extraction_actor_alias_probe.py` metrics for the actor alias
semantic scoring path.

## Follow-up Slice: semantic value-group matching mask precompute

The 2026-07-01 follow-up slice keeps the same registered event-extraction
semantic probe coverage and narrows the hot path in
`_maximum_weight_semantic_value_group_matching()`. The registered
`event-extraction-semantic-value-group-cache` probe now also emits
`matching_elapsed_ms_mean` for the maximum-weight value-group matcher, in
addition to cached value-group construction metrics. Candidate gold/pred index
masks, valid-consumption counts, and numeric scores are now computed once after
candidate ordering instead of being rebuilt on every recursive dynamic-programming
state. Invalid or out-of-range candidates are still ignored, tie-breaking remains
stable, and semantic action split/merge scoring semantics are unchanged.

## Success Metrics

- Focused behavior tests pass.
- Changed-scope coverage for `event_extraction.py` stays above 95%.
- Registered probe mean elapsed time improves or remains within measurement noise
  while preserving output length and normalization call counters.
