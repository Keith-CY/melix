# Serving diagnostics event-line join slice

## Scope

This Python-only performance slice targets the debug serving diagnostics JSONL fast
path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The affected path already has the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json` with
focused test, coverage, and probe commands.

## Change

Keep the empty-attribute event JSONL output byte-for-byte compatible while reducing
intermediate bytes concatenation in `_empty_attribute_event_json_line_bytes` by
assembling the known segments through a single `bytes.join` call.

## Verification plan

- Run focused serving diagnostics tests and PR-scoped probe selection tests.
- Run changed-scope coverage through the registered `coverage_command`.
- Run the registered serving diagnostics queue probe locally on Linux and compare
  `serialization_elapsed_ms_mean` against `origin/main` using the same sample
  count.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
