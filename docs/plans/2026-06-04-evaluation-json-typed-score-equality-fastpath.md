# Evaluation JSON Typed Score Equality Fast Path Plan

## Scope

This Python-only performance slice is limited to JSON final-result typed scoring in
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
The registered workload compares large JSON dictionaries whose scalar and list
subtrees often match exactly.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`. The registry entry already declares focused
`test_command`, `coverage_command`, and `probe_command` values, and the probe
script is `scripts/evaluation_json_typed_score_probe.py`.

## Implementation Slice

- Add a focused regression test proving equal JSON subtrees short-circuit before
  recursive path walking.
- Add a direct equality fast path at the top of `_json_typed_score`.
- Do not change extraction behavior, JSON schema validation, materialization, or
  probe registration.

## Verification

Run the registered focused tests, changed-scope coverage, and the registered
local probe on Linux. GitHub Actions PR-scoped performance remains the merge gate
for base-vs-head evidence.
