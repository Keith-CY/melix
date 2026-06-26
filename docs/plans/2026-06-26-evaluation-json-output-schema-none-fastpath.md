# Evaluation JSON Output Schema None Fast Path

## Scope

This Python-only performance slice is limited to the schema-free JSON final-result
scoring entry point in
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`. The registry entry watches the final-result
implementation, focused tests, `scripts/evaluation_json_typed_score_probe.py`,
and the PR-scoped performance tests, and includes focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Slice

Most schema-free JSON scoring profiles leave `output_schema` as `None`. The hot
entry point previously normalized this to a fresh empty dictionary with
`profile.output_schema or {}` before taking the cached schema-free scoring path.
This slice keeps the same falsy-schema behavior while reading the profile field
directly, avoiding a tiny per-call empty-dict allocation before the LRU cached
scoring helper is consulted.

## Behavior Contract

- `None` and empty-dict output schemas still use the schema-free scoring path.
- Non-empty schemas still run schema validation before scoring.
- JSON parsing, invalid JSON status, typed scoring, and ignored paths are
  unchanged.
- No Swift runtime behavior or generated protobuf artifacts change.

## Verification Plan

1. Run the registered focused test command for
   `evaluation-final-result-json-typed-score-aggregate` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/evaluation_json_typed_score_probe.py` before and after the
   change and accept only if the registered elapsed metric improves or stays
   within bounded noise while allocation does not regress.
4. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Local Results

Baseline direct registered probe on Linux from `origin/main` (`518fc229`):

```json
{"elapsed_ms_mean": 21.269714343361557, "iteration_count": 40.0, "key_count": 2000.0, "peak_bytes_mean": 1189429.6666666667, "score_checksum": 35.0}
```

Post-change direct registered probe on Linux:

```json
{"elapsed_ms_mean": 13.870091800345108, "iteration_count": 40.0, "key_count": 2000.0, "peak_bytes_mean": 713689.8, "score_checksum": 35.0}
```

Focused tests passed (`43 passed`), and changed-scope coverage for the touched
implementation line was `100%`.
