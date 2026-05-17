# Serving diagnostics fast-line bytes slice

## Context

The registered PR-scoped probe `serving-diagnostics-debug-queue-bounds` covers
`services/mlx-worker-python/worker/productization/serving_diagnostics.py` and
runs the focused serving diagnostics tests, changed-scope coverage, and
`scripts/serving_diagnostics_queue_probe.py`.

## Slice

Optimize only the empty-attribute `ServingDiagnosticsEvent` JSONL fast path by
building bytes directly for `_write_jsonl` instead of building a string line and
encoding the complete line again for each event.

## Verification plan

- Run the focused serving diagnostics pytest selection from the registered
  probe.
- Run the registered changed-scope coverage command.
- Run `scripts/serving_diagnostics_queue_probe.py` locally on Linux before and
after the change and compare `serialization_elapsed_ms_mean`.

## Boundary

This is a Python-only Linux-verifiable slice. No Swift runtime validation is
claimed.
