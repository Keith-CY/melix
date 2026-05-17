# Serving diagnostics decode/completed event prefix slice

## Scope

This Python-only performance slice targets the debug serving diagnostics JSONL fast
path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`,
which has focused test, coverage, and probe commands.

## Change

Keep empty-attribute event JSONL output byte-for-byte compatible while adding a
more specific fast path for the common debug probe shape: `phase == "decode"` and
`status == "completed"`. The branch reuses prebuilt byte fragments for the static
JSON prefixes/suffixes and falls back to the generic string-literal path for all
other phases and statuses.

## Verification plan

- Run focused serving diagnostics tests and PR-scoped probe selection tests.
- Run changed-scope coverage through the registered `coverage_command`.
- Run the registered serving diagnostics queue probe locally on Linux and compare
  `serialization_elapsed_ms_mean` against `origin/main` using the same sample
  count.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
