# Event Alignment Late Rounding Performance Slice

## Scope

This slice covers only the Python event-extraction deterministic alignment matcher in
`services/mlx-worker-python/worker/productization/event_extraction.py`.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`event-extraction-alignment-accepted-edge-cache` in
`infra/perf/pr_scoped_probes.json`.

Required focused commands are provided by that probe:

- `test_command` for `services/mlx-worker-python/tests/test_event_extraction.py`
  and the PR-scoped probe smoke test.
- `coverage_command` for changed-scope coverage over the event extraction code,
  the focused tests, and `scripts/event_extraction_alignment_probe.py`.
- `probe_command` for `scripts/event_extraction_alignment_probe.py`.

## Optimization hypothesis

`_accepted_event_matching_edge_states()` currently rounds every accepted sparse
edge before dynamic-programming matching. Only selected matches need rounded
scores for the public result. Deferring `_round_metric()` until a candidate edge
is materialized as a selected pair removes eager rounding from sparse-edge
precomputation while preserving tie-breaking on rounded tuples and the externally
visible rounded match output.

## Verification plan

1. Add/adjust a focused regression assertion showing accepted edge
   precomputation exposes raw sparse edges without calling `_round_metric()`.
2. Run the registered focused tests.
3. Run the registered changed-scope coverage command.
4. Run the registered alignment probe locally on Linux and compare against the
   pre-change baseline captured on this branch before implementation.

## Boundary

This is a Python-only slice, locally validated on Linux. No Swift runtime effect
is claimed.
