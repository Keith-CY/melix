# Statistical Evidence Category Breakdown Local Bindings

## Goal

Reduce per-row overhead in `build_category_breakdown()` while preserving category
filtering, missing-key handling, deterministic ordering, and rounded accuracy
payloads.

## Linux constraint

This is a Python worker/productization slice and is locally verifiable on Linux
with focused pytest, changed-scope coverage, and the registered PR-scoped
performance probe.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`statistical-evidence-category-breakdown-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_category_breakdown_probe.py`

## Optimization

Bind the category totals lookup, string type, and rounding helper once per
function call instead of resolving them repeatedly in the hot row loop or output
materialization loop. For the common probe workload where included rows carry
both correctness keys, use direct key reads with `KeyError` fallback so missing
correctness fields still count as false without paying `dict.get()` method
lookup overhead on every included row.

## Success metrics

- Focused statistical evidence pytest and PR-scoped probe tests pass.
- Changed-scope coverage for touched executable Python/test/probe files remains
  at least 95%.
- The local registered probe reports lower `elapsed_ms_mean` versus the
  pre-change baseline while preserving checksum, row count, and category count.
- GitHub Actions PR-scoped performance completes successfully before merge.
