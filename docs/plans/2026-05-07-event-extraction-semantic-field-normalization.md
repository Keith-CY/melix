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

## Success Metrics

- Focused behavior tests pass.
- Changed-scope coverage for `event_extraction.py` stays above 95%.
- Registered probe mean elapsed time improves or remains within measurement noise
  while preserving output length and normalization call counters.
