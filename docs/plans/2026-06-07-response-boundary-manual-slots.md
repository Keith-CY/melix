# Response Boundary Manual Slots Slice

## Scope

This Python-only performance slice is limited to `ResponseOnlyBoundary` record
construction in `worker.model_ops.response_only_boundary`. The goal is to keep
the response-only boundary record slotted and immutable while trimming the
per-record dataclass construction overhead in large dataset summarization probes.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`response-only-boundary-slotted-records` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/response_only_boundary.py`
- `services/mlx-worker-python/tests/test_response_only_boundary.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/response_only_boundary_slots_probe.py`

## Plan

1. Replace the frozen slotted dataclass wrapper with an explicit slotted record
   that preserves no-`__dict__`, equality, repr, and assignment blocking for the
   persisted manifest boundary fields.
2. Keep aggregate behavior unchanged.
3. Run the focused response-only boundary tests, changed-scope coverage, and the
   registered local probe on Linux.
4. Use PR-scoped performance CI as the base-vs-head merge gate.

## Local Evidence

Initial local probe on `origin/main` with 50k boundaries and 7 samples:

- `construction_elapsed_ms_mean`: `116.496`
- `aggregation_elapsed_ms_mean`: `257.139`
- `peak_bytes_mean`: `3422115.429`

Initial local probe on this slice with the same settings:

- `construction_elapsed_ms_mean`: `115.182`
- `aggregation_elapsed_ms_mean`: `244.501`
- `peak_bytes_mean`: `3422115.429`

The registered CI probe remains the authoritative base-vs-head validation source.
