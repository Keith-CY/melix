# Evaluation JSON Root Equality Fast Path Performance Slice

## Scope

This Python performance slice is limited to
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
`_json_typed_score()` now returns `1.0` immediately when the expected JSON value
and actual JSON value are exactly equal before entering dict/list child scoring.

The behavior is unchanged because exact equality already implies a perfect typed
score. Ignored-path handling still matters for non-identical payloads, so the
slice only short-circuits the exact-match case.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for `evaluation_final_result.py`, its focused tests,
and `scripts/evaluation_json_typed_score_probe.py`.

## Plan

1. Add a regression test proving exact root matches do not iterate dict children.
2. Add one equality fast path at the top of `_json_typed_score()`.
3. Run the focused evaluation final-result tests, changed-scope coverage, and the
   registered evaluation JSON typed-score probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Success Metric

The registered probe should report lower `elapsed_ms_mean` for the JSON typed
score workload while preserving `score_checksum`.
